"""Build falla si /siguiente expone claves secretas."""

from __future__ import annotations

from backend.app.util.secrets import assert_sin_secretos


def test_healthz_sin_db(client):
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_siguiente_no_contiene_secretos(auth_client):
    # Buscar un módulo con banco
    mods = auth_client.get("/api/modulos").json()
    codigo = None
    for m in mods:
        if m.get("en_banco", 0) > 0:
            codigo = m["codigo"]
            break
    assert codigo, "no hay módulos con ítems para la prueba"
    r = auth_client.get(f"/api/modulos/{codigo}/siguiente")
    assert r.status_code == 200, r.text
    body = r.json()
    if body.get("estado") != "pregunta":
        # sin pendientes: aún así no debe haber secretos
        assert_sin_secretos(body)
        return
    assert_sin_secretos(body)
    for op in body["opciones"]:
        assert set(op.keys()) == {"letra", "texto"}
