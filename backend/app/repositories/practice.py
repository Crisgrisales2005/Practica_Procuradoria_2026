"""Acceso a datos de la API: SQL + wrappers srs (siempre con conn=)."""

from __future__ import annotations

from backend.srs.practice import (
    item_completo_para_practica,
    resumen_practica_modulo,
    ultimos_intentos_modulo,
)
from backend.srs.select import siguiente_item
from backend.srs.service import marcar_dudoso, registrar_intento, resolver_unidad_desde_item


def ultimo_intento_id(conn, item_id: int) -> int | None:
    row = conn.execute(
        "SELECT MAX(id) AS m FROM intentos WHERE item_id = %s",
        (item_id,),
    ).fetchone()
    if row is None or row["m"] is None:
        return None
    return int(row["m"])


def en_banco(conn, entidad: str, modulo_codigo: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)::int AS n
        FROM items i
        JOIN modulos m ON m.id = i.modulo_id
        WHERE i.entidad = %s AND m.codigo = %s
        """,
        (entidad, modulo_codigo),
    ).fetchone()
    return int(row["n"] or 0) if row else 0


def listar_modulos_con_banco(conn, entidad: str = "pgn") -> list[dict]:
    rows = conn.execute(
        """
        SELECT m.id, m.entidad, m.codigo, m.nombre, m.tipo, m.orden,
               COUNT(i.id)::int AS en_banco
        FROM modulos m
        LEFT JOIN items i ON i.modulo_id = m.id AND i.entidad = m.entidad
        WHERE m.entidad = %s
        GROUP BY m.id, m.entidad, m.codigo, m.nombre, m.tipo, m.orden
        ORDER BY m.orden
        """,
        (entidad,),
    ).fetchall()
    return [dict(r) for r in rows]


def resumen_modulo(conn, *, entidad: str, modulo_codigo: str) -> dict:
    return resumen_practica_modulo(
        entidad=entidad, modulo_codigo=modulo_codigo, conn=conn
    )


def ultimos_intentos(conn, *, entidad: str, modulo_codigo: str, limit: int = 8) -> list:
    return ultimos_intentos_modulo(
        entidad=entidad, modulo_codigo=modulo_codigo, limit=limit, conn=conn
    )


def seleccionar_siguiente(conn, *, entidad: str, modulo_codigo: str) -> dict | None:
    return siguiente_item(
        entidad=entidad, modulo_codigo=modulo_codigo, conn=conn
    )


def item_completo(conn, item_id: int) -> dict:
    return item_completo_para_practica(item_id, conn=conn)


def advisory_lock_nonce(conn, nonce: str) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (nonce,))


def presentacion_consumida(conn, nonce: str) -> dict | None:
    row = conn.execute(
        """
        SELECT presentacion_id, item_id, intento_id, letra_elegida, puntaje
        FROM presentaciones_consumidas
        WHERE presentacion_id = %s
        """,
        (nonce,),
    ).fetchone()
    return dict(row) if row is not None else None


def insertar_presentacion_consumida(
    conn,
    *,
    nonce: str,
    item_id: int,
    intento_id: int,
    letra: str,
    puntaje: int,
    creado_en: str,
) -> None:
    conn.execute(
        """
        INSERT INTO presentaciones_consumidas (
            presentacion_id, item_id, intento_id, letra_elegida, puntaje, creado_en
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (nonce, item_id, intento_id, letra, puntaje, creado_en),
    )


def registrar(conn, item_id: int, puntaje: int) -> dict:
    return registrar_intento(item_id, puntaje, conn=conn)


def marcar_item_dudoso(conn, item_id: int, dudoso: bool = True) -> dict:
    return marcar_dudoso(item_id, dudoso=dudoso, conn=conn)


def srs_despues_de_item(conn, completo: dict) -> dict | None:
    unidad = resolver_unidad_desde_item(completo)
    row = conn.execute(
        """
        SELECT ease, intervalo_dias, reps, lapses, next_due
        FROM srs_estado
        WHERE entidad = %s AND norma = %s AND articulo = %s
          AND chunk_id = %s AND nivel = %s
        """,
        (
            unidad["entidad"],
            unidad["norma"],
            unidad["articulo"],
            unidad["chunk_id"],
            unidad["nivel"],
        ),
    ).fetchone()
    return dict(row) if row else None


def ping(conn) -> None:
    conn.execute("SELECT 1")
