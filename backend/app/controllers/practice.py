"""Rutas de práctica: módulos, siguiente, intentos, dudoso."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.app.controllers.deps import ENTIDAD, require_auth, require_json
from backend.app.models import DudosoBody, IntentoBody
from backend.app.services import practice as practice_service
from backend.db.connection import get_connection
from backend.srs.service import SrsError

router = APIRouter(tags=["practice"])


@router.get("/api/modulos")
def modulos(request: Request) -> list:
    require_auth(request)
    conn = get_connection()
    try:
        return practice_service.listar_modulos_con_banco(conn, ENTIDAD)
    finally:
        conn.close()


@router.get("/api/modulos/{codigo}/progreso")
def progreso(codigo: str, request: Request) -> dict:
    require_auth(request)
    conn = get_connection()
    try:
        return practice_service.progreso_modulo(
            conn, entidad=ENTIDAD, modulo_codigo=codigo
        )
    finally:
        conn.close()


@router.get("/api/modulos/{codigo}/siguiente")
def siguiente(codigo: str, request: Request) -> dict:
    require_auth(request)
    conn = get_connection()
    try:
        return practice_service.obtener_siguiente(
            conn, entidad=ENTIDAD, modulo_codigo=codigo
        )
    except SrsError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    finally:
        conn.close()


@router.post("/api/intentos")
def intentos(body: IntentoBody, request: Request) -> dict:
    require_auth(request)
    require_json(request)
    conn = get_connection()
    try:
        out = practice_service.responder_intento(
            conn,
            presentacion_token=body.presentacion_token,
            letra=body.letra,
        )
        conn.commit()
        return out
    except LookupError as exc:
        conn.rollback()
        code = str(exc)
        if code == "ya_respondida":
            raise HTTPException(
                status_code=409,
                detail={"error": "Esta pregunta ya fue respondida"},
            ) from exc
        if code == "letra_distinta":
            raise HTTPException(
                status_code=409, detail={"error": "letra_distinta"}
            ) from exc
        raise HTTPException(status_code=409, detail={"error": code}) from exc
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    except SrsError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    except Exception as exc:
        conn.rollback()
        raise HTTPException(
            status_code=500, detail={"error": "error_interno"}
        ) from exc
    finally:
        conn.close()


@router.post("/api/items/{item_id}/dudoso")
def dudoso(item_id: int, body: DudosoBody, request: Request) -> dict:
    require_auth(request)
    require_json(request)
    conn = get_connection()
    try:
        out = practice_service.marcar_item_dudoso(conn, item_id, dudoso=body.dudoso)
        conn.commit()
        return out
    except SrsError as exc:
        conn.rollback()
        raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
