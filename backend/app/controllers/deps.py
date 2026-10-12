"""Helpers HTTP compartidos entre controllers."""

from __future__ import annotations

from fastapi import HTTPException, Request

SESSION_KEY = "auth"
ENTIDAD = "pgn"


def client_ip(request: Request) -> str | None:
    """IP detrás de Render: primer hop de X-Forwarded-For si hay proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def require_auth(request: Request) -> None:
    if not request.session.get(SESSION_KEY):
        raise HTTPException(status_code=401, detail={"error": "no_autenticado"})


def require_json(request: Request) -> None:
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype != "application/json":
        origin = request.headers.get("origin")
        # Alternativa: Origin del mismo despliegue.
        if origin:
            return
        raise HTTPException(
            status_code=415,
            detail={"error": "se_requiere_application_json"},
        )
