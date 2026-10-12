"""Fixtures Fase 9. Crea presentaciones_consumidas si falta (no aplica RLS/rol)."""

from __future__ import annotations

import os

import pytest

# Password de prueba antes de importar settings vía app.
os.environ.setdefault("APP_PASSWORD", "frase-de-prueba-fase9-larga")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-fase9")
os.environ.setdefault("SESSION_HTTPS_ONLY", "0")


@pytest.fixture(scope="session")
def ensure_presentaciones_table():
    from backend.db.connection import get_connection

    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS presentaciones_consumidas (
                presentacion_id TEXT PRIMARY KEY,
                item_id BIGINT NOT NULL REFERENCES items(id),
                intento_id BIGINT NOT NULL REFERENCES intentos(id),
                letra_elegida TEXT NOT NULL CHECK (letra_elegida IN ('A', 'B', 'C', 'D')),
                puntaje INTEGER NOT NULL CHECK (puntaje IN (0, 2, 5)),
                creado_en TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    yield


@pytest.fixture
def client(ensure_presentaciones_table):
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.util import rate_limit

    rate_limit.reset_for_tests()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    r = client.post(
        "/api/auth/login",
        json={"password": os.environ["APP_PASSWORD"]},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    return client
