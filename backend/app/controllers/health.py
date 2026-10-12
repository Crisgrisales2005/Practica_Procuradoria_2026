"""Health checks."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.db.connection import DatabaseError, get_connection, open_pool

router = APIRouter(tags=["health"])


@router.get("/api/healthz")
def healthz() -> dict:
    """Siempre 200; no toca la base (healthCheckPath de Render)."""
    return {"ok": True}


@router.get("/api/health")
def health() -> JSONResponse:
    """Sonda DB para el front. 503 si Supabase aún despierta."""
    try:
        open_pool(wait=True, timeout=10)
        conn = get_connection()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
        return JSONResponse({"ok": True, "db": "ok"})
    except (DatabaseError, Exception):
        return JSONResponse({"ok": True, "db": "warming"}, status_code=503)
