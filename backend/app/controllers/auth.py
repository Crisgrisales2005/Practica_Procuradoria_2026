"""Login / logout / me."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from backend.app.controllers.deps import SESSION_KEY, client_ip, require_auth, require_json
from backend.app.models import LoginBody
from backend.app.services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    require_json(request)
    ip = client_ip(request)
    if not auth_service.login_permitido(ip):
        raise HTTPException(status_code=429, detail={"error": "demasiados_intentos"})

    if not auth_service.password_correcta(body.password):
        auth_service.registrar_fallo(ip)
        raise HTTPException(status_code=401, detail={"error": "password_incorrecta"})

    request.session[SESSION_KEY] = True
    return {"ok": True}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    require_auth(request)
    return {"ok": True}
