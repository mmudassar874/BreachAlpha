"""FastAPI backend for BreachAlpha.

Run with:
    uvicorn breachalpha.server:app --reload --port 8000
"""

from __future__ import annotations

import hmac
import logging
import os

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


# ── Security Constants ───────────────────────────────────────────────────
_ADMIN_KEY = os.environ.get("BREACHALPHA_ADMIN_KEY", "")
_CORS_ORIGINS = os.environ.get(
    "BREACHALPHA_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

# ── Structured Logging ───────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger(__name__)

# ── App ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="BreachAlpha API",
    description="Quantify the financial impact of cybersecurity incidents",
    version="0.1.0",
)

# Rate limiting: in-memory storage (single-server; use Redis for multi-instance)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    headers_enabled=False,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)


# ── Security Middleware ───────────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' http://192.168.56.1:1234 http://localhost:1234; "
            "frame-ancestors 'none'"
        )
        return response


class AdminAuthMiddleware(BaseHTTPMiddleware):
    ADMIN_PREFIXES = ("/api/train", "/api/data-sources/configure")
    ADMIN_EXACT = {"/api/cache"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_admin = (
            any(path.startswith(p) for p in self.ADMIN_PREFIXES)
            or path in self.ADMIN_EXACT
            or (path == "/api/cache" and request.method == "DELETE")
        )
        if is_admin:
            if not _ADMIN_KEY:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Admin endpoints disabled. Set BREACHALPHA_ADMIN_KEY environment variable."},
                )
            key = request.headers.get("X-Admin-Key", "")
            if not hmac.compare_digest(key, _ADMIN_KEY):
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing X-Admin-Key header"},
                )
        return await call_next(request)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AdminAuthMiddleware)


# ── Domain Exception → HTTP Response Translation ──────────────────────────
from .core.exceptions import (
    BreachAlphaError, TickerResolutionError, InvalidTickerError,
    NoStockDataError, InsufficientDataError, UnsupportedFileTypeError,
    FileTooLargeError, LLMUnavailableError, TrainingError,
)
from fastapi.responses import JSONResponse

_exception_status_map: dict[type, int] = {
    TickerResolutionError: 404,
    InvalidTickerError: 400,
    NoStockDataError: 404,
    InsufficientDataError: 422,
    UnsupportedFileTypeError: 400,
    FileTooLargeError: 413,
    LLMUnavailableError: 503,
    TrainingError: 422,
}


@app.exception_handler(BreachAlphaError)
async def breach_alpha_error_handler(request: Request, exc: BreachAlphaError):
    status = _exception_status_map.get(type(exc), 500)
    return JSONResponse(status_code=status, content={"detail": str(exc)})


# ── Register Routes ──────────────────────────────────────────────────────
from .routes.meta import create_meta_routes
from .routes.score import create_score_routes
from .routes.upload import create_upload_routes
from .routes.explain import create_explain_routes
from .routes.search import create_search_routes
from .routes.llm import create_llm_routes
from .routes.admin import create_admin_routes

for create_routes in [
    create_meta_routes,
    create_score_routes,
    create_upload_routes,
    create_explain_routes,
    create_search_routes,
    create_llm_routes,
    create_admin_routes,
]:
    app.include_router(create_routes(limiter))


# ── Static File Serving (Production) ──────────────────────────────────────
from pathlib import Path
from fastapi.responses import FileResponse

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for all non-API routes."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        resolved = (FRONTEND_DIR / full_path).resolve()
        if not str(resolved).startswith(str(FRONTEND_DIR.resolve())):
            return FileResponse(FRONTEND_DIR / "index.html")
        if resolved.exists() and resolved.is_file():
            return FileResponse(resolved)
        return FileResponse(FRONTEND_DIR / "index.html")
