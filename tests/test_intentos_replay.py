"""Primer POST + mismo POST → 200 replay, no 409."""

from __future__ import annotations


def _modulo_con_pregunta(auth_client) -> tuple[str, dict]:
    mods = auth_client.get("/api/modulos").json()
    for m in mods:
        if m.get("en_banco", 0) > 0:
            codigo = m["codigo"]
            r = auth_client.get(f"/api/modulos/{codigo}/siguiente")
            assert r.status_code == 200, r.text
            body = r.json()
            if body.get("estado") == "pregunta":
                return codigo, body
    raise AssertionError("no hay pregunta pendiente en ningún módulo")


def test_mismo_post_replay_200(auth_client):
    _codigo, pregunta = _modulo_con_pregunta(auth_client)
    token = pregunta["presentacion_token"]
    letra = pregunta["opciones"][0]["letra"]
    payload = {"presentacion_token": token, "letra": letra}
    headers = {"Content-Type": "application/json"}

    r1 = auth_client.post("/api/intentos", json=payload, headers=headers)
    assert r1.status_code == 200, r1.text
    fb1 = r1.json()
    assert fb1["estado"] == "feedback"
    assert fb1["letra_elegida"] == letra

    r2 = auth_client.post("/api/intentos", json=payload, headers=headers)
    assert r2.status_code == 200, r2.text
    fb2 = r2.json()
    assert fb2["estado"] == "feedback"
    assert fb2["letra_elegida"] == fb1["letra_elegida"]
    assert fb2["puntaje"] == fb1["puntaje"]
    assert fb2["matriz"] == fb1["matriz"]
