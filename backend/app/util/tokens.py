"""Tokens de presentación firmados (sin estado en cookie)."""

from __future__ import annotations

import uuid
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from backend.config import settings

_MAX_AGE_S = 2 * 60 * 60


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        settings.session_secret, salt="procuradoria-presentacion-v1"
    )


def firmar_presentacion(
    *, item_id: int, ultimo_intento_id: int | None
) -> str:
    payload = {
        "v": 1,
        "item_id": int(item_id),
        "nonce": str(uuid.uuid4()),
        "ultimo_intento_id": ultimo_intento_id,
    }
    return _serializer().dumps(payload)


def verificar_presentacion(token: str) -> dict[str, Any]:
    try:
        data = _serializer().loads(token, max_age=_MAX_AGE_S)
    except SignatureExpired as exc:
        raise ValueError("presentacion_expirada") from exc
    except BadSignature as exc:
        raise ValueError("presentacion_invalida") from exc
    if not isinstance(data, dict) or int(data.get("v") or 0) != 1:
        raise ValueError("presentacion_invalida")
    item_id = data.get("item_id")
    nonce = data.get("nonce")
    if item_id is None or not nonce:
        raise ValueError("presentacion_invalida")
    ultimo = data.get("ultimo_intento_id")
    return {
        "item_id": int(item_id),
        "nonce": str(nonce),
        "ultimo_intento_id": int(ultimo) if ultimo is not None else None,
    }
