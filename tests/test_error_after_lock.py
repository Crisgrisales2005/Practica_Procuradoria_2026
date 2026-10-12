"""Excepción tras el lock: conn limpia y siguiente petición OK."""

from __future__ import annotations

import pytest

from backend.app.services import practice as practice_service


def _pregunta(auth_client) -> dict:
    mods = auth_client.get("/api/modulos").json()
    for m in mods:
        if m.get("en_banco", 0) > 0:
            r = auth_client.get(f"/api/modulos/{m['codigo']}/siguiente")
            body = r.json()
            if body.get("estado") == "pregunta":
                return body
    pytest.skip("sin pregunta pendiente")


def test_error_after_lock_limpia_pool(auth_client):
    pregunta = _pregunta(auth_client)
    token = pregunta["presentacion_token"]
    letra = pregunta["opciones"][0]["letra"]
    headers = {"Content-Type": "application/json"}
    payload = {"presentacion_token": token, "letra": letra}

    practice_service.set_force_error_after_lock(True)
    try:
        r = auth_client.post("/api/intentos", json=payload, headers=headers)
        assert r.status_code == 500
    finally:
        practice_service.set_force_error_after_lock(False)

    # Misma presentación debe poder completarse ahora (lock liberado, conn limpia).
    r2 = auth_client.post("/api/intentos", json=payload, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["estado"] == "feedback"

    # Health / siguiente siguen respondiendo.
    assert auth_client.get("/api/healthz").status_code == 200
    assert auth_client.get("/api/modulos").status_code == 200
