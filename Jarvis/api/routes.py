"""
API Routes — REST endpoints for the mobile companion app.
============================================================
Provides endpoints for:
  - Command execution (voice/text → Orchestrator → response)
  - System status (CPU, memory, active model)
  - Memory management (list/add/delete memories)
  - Workflow triggers
  - Vision queries
"""

import logging
import time
from typing import Optional

logger = logging.getLogger("jarvis.api.routes")

try:
    from fastapi import APIRouter, HTTPException, Depends, Header
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning("fastapi not installed. API routes disabled. pip install fastapi")

if FASTAPI_AVAILABLE:
    from Jarvis.api.auth import validate_token

    router = APIRouter(prefix="/api/v1")

    # ── Auth dependency ──────────────────────────────────────────────────

    async def verify_auth(authorization: str = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        token = authorization.replace("Bearer ", "")
        if not validate_token(token):
            raise HTTPException(status_code=403, detail="Invalid API token")

    # ── Request/Response Models ──────────────────────────────────────────

    class CommandRequest(BaseModel):
        text: str
        context: Optional[str] = None

    class CommandResponse(BaseModel):
        response: str
        elapsed_ms: float
        model: str = ""

    class StatusResponse(BaseModel):
        status: str
        uptime_seconds: float
        active_model: str
        plugins_loaded: int
        memory_count: int

    class MemoryItem(BaseModel):
        id: int = 0
        fact: str
        source: str = ""
        confidence: float = 0.0

    class SearchRequest(BaseModel):
        query: str
        max_results: int = 5

    # ── Endpoints ────────────────────────────────────────────────────────

    _start_time = time.time()
    _orchestrator = None

    def set_orchestrator(orchestrator):
        """Inject the Orchestrator instance (called at server startup)."""
        global _orchestrator
        _orchestrator = orchestrator

    @router.get("/health")
    async def health():
        return {"status": "ok", "uptime": time.time() - _start_time}

    @router.get("/status", response_model=StatusResponse, dependencies=[Depends(verify_auth)])
    async def get_status():
        from Jarvis.config import OLLAMA_MODEL, LLM_PROVIDER

        uptime = time.time() - _start_time
        model = OLLAMA_MODEL if LLM_PROVIDER == "ollama" else f"{LLM_PROVIDER}"

        memory_count = 0
        try:
            from Jarvis.core.memory_engine import get_memory_engine
            stats = get_memory_engine().get_memory_count()
            memory_count = stats.get("total", 0)
        except Exception:
            pass

        plugins = 0
        try:
            from Jarvis.core.plugins.registry import get_plugin_registry
            plugins = len(get_plugin_registry().enabled_plugins)
        except Exception:
            pass

        return StatusResponse(
            status="running",
            uptime_seconds=uptime,
            active_model=model,
            plugins_loaded=plugins,
            memory_count=memory_count,
        )

    @router.post("/command", response_model=CommandResponse, dependencies=[Depends(verify_auth)])
    async def execute_command(req: CommandRequest):
        if not _orchestrator:
            raise HTTPException(status_code=503, detail="Orchestrator not initialized")

        t0 = time.time()
        response = _orchestrator.process_command(req.text)
        elapsed = (time.time() - t0) * 1000

        return CommandResponse(
            response=response,
            elapsed_ms=elapsed,
        )

    @router.get("/memories", dependencies=[Depends(verify_auth)])
    async def list_memories():
        try:
            from Jarvis.core.memory_engine import get_memory_engine
            memories = get_memory_engine().get_all_memories()
            return {"memories": memories}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/memories", dependencies=[Depends(verify_auth)])
    async def add_memory(item: MemoryItem):
        try:
            from Jarvis.core.memory_engine import get_memory_engine
            success = get_memory_engine().add_explicit(item.fact, context="API")
            return {"success": success, "fact": item.fact}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/memories/{memory_id}", dependencies=[Depends(verify_auth)])
    async def delete_memory(memory_id: int):
        try:
            from Jarvis.core.memory_engine import get_memory_engine
            success = get_memory_engine().delete_memory(memory_id)
            return {"success": success}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/search", dependencies=[Depends(verify_auth)])
    async def web_search(req: SearchRequest):
        from Jarvis.core.web_search import web_search as ws, format_search_results
        response = ws(req.query, max_results=req.max_results)
        return {
            "query": req.query,
            "results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in response.results
            ],
            "answer": response.answer,
            "error": response.error,
        }

    @router.get("/plugins", dependencies=[Depends(verify_auth)])
    async def list_plugins():
        try:
            from Jarvis.core.plugins.registry import get_plugin_registry
            return {"plugins": get_plugin_registry().status_report()}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
