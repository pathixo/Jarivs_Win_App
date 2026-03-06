"""
Compute Node — Worker node that connects to the dispatcher via WebSocket.
===========================================================================
Each node registers its capabilities (GPU, Ollama, TTS) and receives
tasks from the dispatcher. Runs as a background service.
"""

import asyncio
import json
import logging
import platform
import socket
import threading
import time
import uuid
from typing import Optional, Callable

from Jarvis.core.compute.protocol import (
    ProtocolMessage, MessageType, NodeInfo, TaskMessage,
)

logger = logging.getLogger("jarvis.compute.node")

try:
    import websockets
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False


class ComputeNode:
    """
    A worker node that connects to a central dispatcher.

    Registers capabilities, receives tasks, executes them locally,
    and returns results over WebSocket.
    """

    def __init__(
        self,
        dispatcher_url: str = "ws://localhost:8743",
        capabilities: list[str] = None,
        max_concurrent: int = 2,
    ):
        self._dispatcher_url = dispatcher_url
        self._node_id = str(uuid.uuid4())[:8]
        self._hostname = platform.node()
        self._ip = self._get_local_ip()
        self._capabilities = capabilities or ["llm_inference"]
        self._max_concurrent = max_concurrent
        self._running = False
        self._ws = None
        self._task_handlers: dict[str, Callable] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def info(self) -> NodeInfo:
        return NodeInfo(
            node_id=self._node_id,
            hostname=self._hostname,
            ip=self._ip,
            port=0,
            capabilities=self._capabilities,
            max_concurrent=self._max_concurrent,
            status="busy" if self._active_tasks else "idle",
        )

    def register_handler(self, task_type: str, handler: Callable) -> None:
        """Register a handler function for a specific task type."""
        self._task_handlers[task_type] = handler

    def start(self) -> None:
        """Start the node in a background thread."""
        if not WS_AVAILABLE:
            raise ImportError("websockets required. pip install websockets")

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="compute-node")
        self._thread.start()
        logger.info("Compute node started: %s", self._node_id)

    def stop(self) -> None:
        """Stop the node."""
        self._running = False
        logger.info("Compute node stopping: %s", self._node_id)

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        """Continuously attempt to connect to the dispatcher."""
        while self._running:
            try:
                async with websockets.connect(self._dispatcher_url) as ws:
                    self._ws = ws
                    logger.info("Connected to dispatcher: %s", self._dispatcher_url)

                    # Register
                    await self._send(MessageType.REGISTER, {
                        "node": self.info.__dict__,
                    })

                    # Start heartbeat
                    asyncio.ensure_future(self._heartbeat_loop())

                    # Listen for tasks
                    async for raw in ws:
                        msg = ProtocolMessage.deserialize(raw)
                        await self._handle_message(msg)

            except Exception as e:
                logger.warning("Connection to dispatcher failed: %s. Retrying in 5s...", e)
                await asyncio.sleep(5)

    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        while self._running and self._ws:
            try:
                await self._send(MessageType.HEARTBEAT, {
                    "active_tasks": len(self._active_tasks),
                    "status": "busy" if self._active_tasks else "idle",
                })
                await asyncio.sleep(10)
            except Exception:
                break

    async def _handle_message(self, msg: ProtocolMessage):
        """Process an incoming message from the dispatcher."""
        if msg.msg_type == MessageType.TASK_ASSIGN:
            task_type = msg.data.get("task_type", "")
            task_id = msg.data.get("task_id", "")

            handler = self._task_handlers.get(task_type)
            if handler:
                # Execute task asynchronously
                task = asyncio.ensure_future(
                    self._execute_task(task_id, task_type, msg.data.get("payload", {}), handler)
                )
                self._active_tasks[task_id] = task
            else:
                await self._send(MessageType.TASK_ERROR, {
                    "task_id": task_id,
                    "error": f"No handler for task type: {task_type}",
                })

        elif msg.msg_type == MessageType.TASK_CANCEL:
            task_id = msg.data.get("task_id", "")
            if task_id in self._active_tasks:
                self._active_tasks[task_id].cancel()
                del self._active_tasks[task_id]

    async def _execute_task(self, task_id: str, task_type: str, payload: dict, handler: Callable):
        """Execute a task and send the result back."""
        try:
            # Run handler in a thread pool (avoid blocking the event loop)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, handler, payload)

            await self._send(MessageType.TASK_RESULT, {
                "task_id": task_id,
                "result": result,
            })

        except Exception as e:
            await self._send(MessageType.TASK_ERROR, {
                "task_id": task_id,
                "error": str(e),
            })
        finally:
            self._active_tasks.pop(task_id, None)

    async def _send(self, msg_type: MessageType, data: dict):
        """Send a protocol message to the dispatcher."""
        if self._ws:
            msg = ProtocolMessage(
                msg_type=msg_type,
                sender_id=self._node_id,
                timestamp=time.time(),
                data=data,
            )
            await self._ws.send(msg.serialize())
