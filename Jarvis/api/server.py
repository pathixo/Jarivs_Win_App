"""
API Server — FastAPI + Uvicorn server for mobile companion connectivity.
==========================================================================
Starts a local HTTP server that exposes the Jarvis API to devices on the
same network. Supports auto-discovery via mDNS (optional).

Usage:
    from Jarvis.api.server import start_api_server
    start_api_server(port=8742)
"""

import logging
import socket
import threading
from typing import Optional

logger = logging.getLogger("jarvis.api.server")

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def get_local_ip() -> str:
    """Get the machine's local network IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# Trusted browser origins for CORS.
# NOTE: The mobile companion app is a native HTTP client, not a browser, so it
# is NOT subject to CORS and will work regardless of this list.  This list only
# affects browser-based clients (e.g. the /docs UI or a web dashboard running
# on localhost).  Wildcard ("*") is intentionally avoided: combined with
# allow_credentials it is rejected by browsers anyway, and even without
# credentials it would allow any malicious website to probe the local API.
TRUSTED_ORIGINS: list[str] = [
    "http://localhost",
    "http://localhost:8742",
    "http://127.0.0.1",
    "http://127.0.0.1:8742",
]


def create_app() -> "FastAPI":
    """Create and configure the FastAPI application."""
    if not FASTAPI_AVAILABLE:
        raise ImportError("fastapi and uvicorn required. pip install fastapi uvicorn")

    app = FastAPI(
        title="Jarvis API",
        description="Mobile companion REST API for Jarvis AI Assistant",
        version="2.0.0",
    )

    # CORS — restricted to localhost browser origins only.
    # All sensitive endpoints are additionally protected by Bearer-token auth
    # (see Jarvis/api/routes.py → verify_auth).  allow_credentials is False
    # because auth is carried in the Authorization header, not cookies.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=TRUSTED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Register routes
    from Jarvis.api.routes import router
    app.include_router(router)

    @app.get("/")
    async def root():
        return {
            "name": "Jarvis AI",
            "version": "2.0.0",
            "ip": get_local_ip(),
            "docs": "/docs",
        }

    return app


_server_thread: Optional[threading.Thread] = None
_server_instance: Optional["uvicorn.Server"] = None


def start_api_server(port: int = 8742, host: str = "0.0.0.0") -> dict:
    """
    Start the API server in a background thread.

    Args:
        port: Port to listen on (default: 8742)
        host: Host to bind to (default: 0.0.0.0 for network access)

    Returns:
        dict with server info (ip, port, url)
    """
    global _server_thread, _server_instance

    if not FASTAPI_AVAILABLE:
        return {"error": "fastapi/uvicorn not installed"}

    if _server_thread and _server_thread.is_alive():
        return {"error": "Server already running", "url": f"http://{get_local_ip()}:{port}"}

    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    _server_instance = uvicorn.Server(config)

    def _run():
        _server_instance.run()

    _server_thread = threading.Thread(target=_run, daemon=True, name="api-server")
    _server_thread.start()

    local_ip = get_local_ip()
    info = {
        "ip": local_ip,
        "port": port,
        "url": f"http://{local_ip}:{port}",
        "docs": f"http://{local_ip}:{port}/docs",
        "token_hint": "Use GET /api/v1/health to test (no auth required)",
    }
    logger.info("API server started at %s", info["url"])
    return info


def stop_api_server():
    """Gracefully stop the API server."""
    global _server_instance
    if _server_instance:
        _server_instance.should_exit = True
        logger.info("API server stopped")
