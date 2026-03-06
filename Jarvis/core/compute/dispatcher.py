"""
Compute Dispatcher — Central task coordinator for distributed compute.
========================================================================
Manages worker nodes, distributes tasks, handles failover, and tracks
results. Runs as a WebSocket server.

Features:
  - Node registration and health monitoring
  - Task assignment based on capabilities and load
  - Automatic failover when a node goes offline
  - Cloud API fallback for critical tasks
  - Task result aggregation
"""

import asyncio
import json
import logging
import time
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Callable

from Jarvis.core.compute.protocol import (
    ProtocolMessage, MessageType, NodeInfo, TaskMessage,
)

logger = logging.getLogger("jarvis.compute.dispatcher")

try:
    import websockets
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False


@dataclass
class RegisteredNode:
    """A node tracked by the dispatcher."""
    info: NodeInfo
    ws: object = None               # WebSocket connection
    last_heartbeat: float = 0.0
    active_task_count: int = 0


class TaskDispatcher:
    """
    Central dispatcher that coordinates work across compute nodes.

    Usage:
        dispatcher = TaskDispatcher()
        dispatcher.start(port=8743)

        # Submit tasks
        result = await dispatcher.submit("llm_inference", {"prompt": "Hello"})
    """

    HEARTBEAT_TIMEOUT = 30.0   # Node considered dead after this
    TASK_TIMEOUT = 60.0        # Default task timeout

    def __init__(self, cloud_fallback: Optional[Callable] = None):
        self._nodes: dict[str, RegisteredNode] = {}
        self._pending_tasks: dict[str, TaskMessage] = {}
        self._completed_tasks: dict[str, TaskMessage] = {}
        self._task_futures: dict[str, asyncio.Future] = {}
        self._cloud_fallback = cloud_fallback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def nodes(self) -> dict[str, RegisteredNode]:
        return dict(self._nodes)

    @property
    def online_nodes(self) -> list[RegisteredNode]:
        now = time.time()
        return [
            n for n in self._nodes.values()
            if now - n.last_heartbeat < self.HEARTBEAT_TIMEOUT
        ]

    # ── Server ───────────────────────────────────────────────────────────

    def start(self, host: str = "0.0.0.0", port: int = 8743) -> None:
        """Start the dispatcher WebSocket server in a background thread."""
        if not WS_AVAILABLE:
            raise ImportError("websockets required. pip install websockets")

        self._running = True
        self._thread = threading.Thread(
            target=self._run_server, args=(host, port), daemon=True, name="dispatcher"
        )
        self._thread.start()
        logger.info("Dispatcher started on ws://%s:%d", host, port)

    def _run_server(self, host: str, port: int):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._serve(host, port))

    async def _serve(self, host: str, port: int):
        async with websockets.serve(self._handler, host, port):
            # Start health checker
            asyncio.ensure_future(self._health_check_loop())
            await asyncio.Future()  # Run forever

    async def _handler(self, ws, path=None):
        """Handle incoming WebSocket connections from nodes."""
        node_id = None
        try:
            async for raw in ws:
                msg = ProtocolMessage.deserialize(raw)
                node_id = msg.sender_id

                if msg.msg_type == MessageType.REGISTER:
                    node_info = NodeInfo(**msg.data.get("node", {}))
                    self._nodes[node_id] = RegisteredNode(
                        info=node_info,
                        ws=ws,
                        last_heartbeat=time.time(),
                    )
                    logger.info("Node registered: %s (%s)", node_id, node_info.hostname)

                    # ACK
                    await ws.send(ProtocolMessage(
                        msg_type=MessageType.ACK,
                        sender_id="dispatcher",
                        timestamp=time.time(),
                        data={"message": "Registered successfully"},
                    ).serialize())

                elif msg.msg_type == MessageType.HEARTBEAT:
                    if node_id in self._nodes:
                        self._nodes[node_id].last_heartbeat = time.time()
                        self._nodes[node_id].active_task_count = msg.data.get("active_tasks", 0)

                elif msg.msg_type == MessageType.TASK_RESULT:
                    task_id = msg.data.get("task_id", "")
                    if task_id in self._pending_tasks:
                        task = self._pending_tasks.pop(task_id)
                        task.result = msg.data.get("result")
                        task.completed_at = time.time()
                        self._completed_tasks[task_id] = task

                        # Resolve the future
                        if task_id in self._task_futures:
                            fut = self._task_futures.pop(task_id)
                            if not fut.done():
                                fut.set_result(task.result)

                elif msg.msg_type == MessageType.TASK_ERROR:
                    task_id = msg.data.get("task_id", "")
                    error = msg.data.get("error", "Unknown error")
                    logger.error("Task %s failed on node %s: %s", task_id, node_id, error)

                    if task_id in self._pending_tasks:
                        task = self._pending_tasks.pop(task_id)
                        task.error = error

                        # Try failover to another node or cloud
                        await self._handle_failover(task)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("Node disconnected: %s", node_id)
        finally:
            if node_id and node_id in self._nodes:
                self._nodes[node_id].info.status = "offline"

    # ── Task Submission ──────────────────────────────────────────────────

    async def submit(
        self,
        task_type: str,
        payload: dict,
        priority: int = 0,
        timeout_s: float = None,
    ) -> any:
        """
        Submit a task for distributed execution.

        Finds the best available node and assigns the task.
        Falls back to cloud API if no nodes are available.

        Returns the task result.
        """
        timeout_s = timeout_s or self.TASK_TIMEOUT
        task_id = str(uuid.uuid4())[:12]

        task = TaskMessage(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            priority=priority,
            timeout_s=timeout_s,
            created_at=time.time(),
        )

        # Find the best node
        node = self._find_best_node(task_type)

        if node:
            return await self._assign_to_node(task, node)
        elif self._cloud_fallback:
            logger.info("No nodes available for %s, using cloud fallback", task_type)
            return self._cloud_fallback(task_type, payload)
        else:
            raise RuntimeError(f"No compute nodes available for task type: {task_type}")

    def _find_best_node(self, task_type: str) -> Optional[RegisteredNode]:
        """Find the least-loaded node with the required capability."""
        candidates = [
            n for n in self.online_nodes
            if task_type in n.info.capabilities
            and n.active_task_count < n.info.max_concurrent
        ]

        if not candidates:
            return None

        # Pick the one with the fewest active tasks
        return min(candidates, key=lambda n: n.active_task_count)

    async def _assign_to_node(self, task: TaskMessage, node: RegisteredNode) -> any:
        """Assign a task to a specific node and wait for the result."""
        task.assigned_node = node.info.node_id
        self._pending_tasks[task.task_id] = task
        node.active_task_count += 1

        # Create a future for the result
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._task_futures[task.task_id] = fut

        # Send the task to the node
        msg = ProtocolMessage(
            msg_type=MessageType.TASK_ASSIGN,
            sender_id="dispatcher",
            timestamp=time.time(),
            data={
                "task_id": task.task_id,
                "task_type": task.task_type,
                "payload": task.payload,
            },
        )
        await node.ws.send(msg.serialize())

        # Wait for result with timeout
        try:
            result = await asyncio.wait_for(fut, timeout=task.timeout_s)
            return result
        except asyncio.TimeoutError:
            self._pending_tasks.pop(task.task_id, None)
            self._task_futures.pop(task.task_id, None)
            raise TimeoutError(f"Task {task.task_id} timed out after {task.timeout_s}s")

    async def _handle_failover(self, task: TaskMessage):
        """Try to reassign a failed task to another node or cloud."""
        # Find another node (excluding the one that failed)
        candidates = [
            n for n in self.online_nodes
            if n.info.node_id != task.assigned_node
            and task.task_type in n.info.capabilities
        ]

        if candidates:
            logger.info("Failing over task %s to another node", task.task_id)
            await self._assign_to_node(task, candidates[0])
        elif self._cloud_fallback:
            logger.info("Failing over task %s to cloud", task.task_id)
            try:
                result = self._cloud_fallback(task.task_type, task.payload)
                if task.task_id in self._task_futures:
                    fut = self._task_futures.pop(task.task_id)
                    if not fut.done():
                        fut.set_result(result)
            except Exception as e:
                logger.error("Cloud fallback failed: %s", e)
        else:
            logger.error("No failover available for task %s", task.task_id)

    # ── Health Monitoring ────────────────────────────────────────────────

    async def _health_check_loop(self):
        """Periodically check node health and mark offline nodes."""
        while self._running:
            now = time.time()
            for node_id, node in list(self._nodes.items()):
                if now - node.last_heartbeat > self.HEARTBEAT_TIMEOUT:
                    if node.info.status != "offline":
                        node.info.status = "offline"
                        logger.warning("Node %s (%s) went offline", node_id, node.info.hostname)
            await asyncio.sleep(10)

    # ── Status ───────────────────────────────────────────────────────────

    def status_report(self) -> dict:
        """Return a summary of the compute cluster."""
        return {
            "total_nodes": len(self._nodes),
            "online_nodes": len(self.online_nodes),
            "pending_tasks": len(self._pending_tasks),
            "completed_tasks": len(self._completed_tasks),
            "nodes": [
                {
                    "id": n.info.node_id,
                    "host": n.info.hostname,
                    "status": n.info.status,
                    "capabilities": n.info.capabilities,
                    "active_tasks": n.active_task_count,
                    "last_heartbeat": n.last_heartbeat,
                }
                for n in self._nodes.values()
            ],
        }

    def stop(self):
        """Stop the dispatcher."""
        self._running = False


# ── Module singleton ────────────────────────────────────────────────────

_dispatcher: Optional[TaskDispatcher] = None


def get_dispatcher() -> TaskDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = TaskDispatcher()
    return _dispatcher
