"""E2E como procuradoria_web por Session pooler.

Requiere DATABASE_URL_WEB (usuario procuradoria_web.<ref>) tras aplicar
migrate_fase9_web.sql. Si no está definida, se omite.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL_WEB"),
    reason="Define DATABASE_URL_WEB tras aplicar la migración Fase 9",
)


@pytest.fixture
def web_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL_WEB"])
    monkeypatch.setenv("APP_PASSWORD", os.environ.get("APP_PASSWORD", "frase-de-prueba-fase9-larga"))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-fase9")
    monkeypatch.setenv("SESSION_HTTPS_ONLY", "0")

    # Reiniciar pool con la URL del rol web.
    import backend.db.connection as conn_mod
    import backend.config as config_mod

    config_mod.settings = config_mod.load_settings()
    conn_mod._pool = None
    conn_mod._pool_opened = False

    from fastapi.testclient import TestClient
    import importlib
    import backend.app.main as app_mod

    importlib.reload(app_mod)
    from backend.app.util import rate_limit

    rate_limit.reset_for_tests()
    with TestClient(app_mod.app) as c:
        yield c

    conn_mod._pool = None
    conn_mod._pool_opened = False


def test_flujo_completo_rol_web(web_client):
    assert web_client.get("/api/healthz").status_code == 200
    h = web_client.get("/api/health")
    assert h.status_code in (200, 503)

    pw = os.environ.get("APP_PASSWORD", "frase-de-prueba-fase9-larga")
    r = web_client.post(
        "/api/auth/login",
        json={"password": pw},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text

    mods = web_client.get("/api/modulos")
    assert mods.status_code == 200, mods.text
    # permission denied en chunks no debería aparecer aquí
    assert "permission denied" not in mods.text.lower()

    codigo = None
    for m in mods.json():
        if m.get("en_banco", 0) > 0:
            codigo = m["codigo"]
            break
    assert codigo

    prog = web_client.get(f"/api/modulos/{codigo}/progreso")
    assert prog.status_code == 200, prog.text

    sig = web_client.get(f"/api/modulos/{codigo}/siguiente")
    assert sig.status_code == 200, sig.text
    body = sig.json()
    if body.get("estado") != "pregunta":
        pytest.skip("sin pendientes")

    letra = body["opciones"][0]["letra"]
    payload = {
        "presentacion_token": body["presentacion_token"],
        "letra": letra,
    }
    headers = {"Content-Type": "application/json"}
    r1 = web_client.post("/api/intentos", json=payload, headers=headers)
    assert r1.status_code == 200, r1.text
    r2 = web_client.post("/api/intentos", json=payload, headers=headers)
    assert r2.status_code == 200, r2.text

    item_id = body["item_id"]
    d = web_client.post(
        f"/api/items/{item_id}/dudoso",
        json={"dudoso": True},
        headers=headers,
    )
    assert d.status_code == 200, d.text
    # quitar dudoso para no ensuciar la cola
    web_client.post(
        f"/api/items/{item_id}/dudoso",
        json={"dudoso": False},
        headers=headers,
    )
