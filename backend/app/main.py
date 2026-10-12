"""Entry FastAPI: monta routers y estáticos del SPA."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from backend.app.controllers import auth, health, practice
from backend.config import settings

app = FastAPI(title="Preparación Sustanciador 4SU-11", docs_url=None, redoc_url=None)

# Cookie Secure solo bajo HTTPS (Render) o si SESSION_HTTPS_ONLY=1.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="procuradoria_session",
    https_only=settings.session_https_only,
    same_site="lax",
    max_age=60 * 60 * 24 * 14,
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(practice.router)

# Estáticos del SPA (tras build). En desarrollo pueden no existir.
_STATIC = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _STATIC.is_dir():
    assets = _STATIC / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        # No interceptar /api
        if full_path.startswith("api"):
            raise HTTPException(status_code=404)
        candidate = _STATIC / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC / "index.html")
