"""Selección del siguiente ítem: vencidos antes que nuevos; excluye dudoso."""

from __future__ import annotations

import json
from typing import Any

from backend.db.connection import get_connection
from backend.srs.sm2 import NIVEL_CASO, iso_utc, utc_now


def _chunk_id_de_item(chunk_ids_raw: str | None) -> int | None:
    """Lee el primer chunk_id del JSON del ítem, o None si no se puede.

    Cómo: igual que en el registro de intentos, pero aquí un JSON roto o una
    lista vacía no lanza error: la pregunta se salta al elegir la siguiente.

    Variables:
        chunk_ids_raw: texto de `items.chunk_ids`.
        ids: lista parseada.

    Devuelve: el id entero, o None.
    """
    # asume 1 solo chunk_id; revisar si algún día se soportan ítems multi-fragmento
    try:
        ids = json.loads(chunk_ids_raw or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(ids, list) or not ids:
        return None
    try:
        return int(ids[0])
    except (TypeError, ValueError):
        return None


def siguiente_item(
    *,
    entidad: str = "pgn",
    modulo_codigo: str = "esp_08",
    excluir_ids: set[int] | frozenset[int] | None = None,
    conn=None,
) -> dict[str, Any] | None:
    """Elige la próxima pregunta. Si `conn` se pasa, no abre otra."""
    ahora = iso_utc(utc_now())
    omitidos = set(excluir_ids or ())
    own = conn is None
    if own:
        conn = get_connection()
    try:
        mod = conn.execute(
            """
            SELECT id FROM modulos
            WHERE entidad = %s AND codigo = %s
            """,
            (entidad, modulo_codigo),
        ).fetchone()
        if mod is None:
            return None
        modulo_id = int(mod["id"])

        candidatos = conn.execute(
            """
            SELECT i.id, i.entidad, i.modulo_id, i.norma, i.articulo,
                   i.chunk_ids, i.enunciado, i.caso, i.dudoso, i.creado_en
            FROM items i
            WHERE i.entidad = %s
              AND i.modulo_id = %s
              AND i.dudoso = 0
            ORDER BY i.id ASC
            """,
            (entidad, modulo_id),
        ).fetchall()

        # 1) Vencidos
        mejor_vencido: dict[str, Any] | None = None
        for row in candidatos:
            if int(row["id"]) in omitidos:
                continue
            chunk_id = _chunk_id_de_item(row["chunk_ids"])
            if chunk_id is None:
                continue
            srs = conn.execute(
                """
                SELECT next_due, ease, intervalo_dias, reps, lapses
                FROM srs_estado
                WHERE entidad = %s AND norma = %s
                  AND articulo = %s AND chunk_id = %s AND nivel = %s
                """,
                (
                    row["entidad"],
                    row["norma"],
                    row["articulo"],
                    chunk_id,
                    NIVEL_CASO,
                ),
            ).fetchone()
            if srs is None or not srs["next_due"]:
                continue
            if str(srs["next_due"]) > ahora:
                continue
            cand = dict(row)
            cand.update(
                {
                    "next_due": srs["next_due"],
                    "ease": srs["ease"],
                    "intervalo_dias": srs["intervalo_dias"],
                    "reps": srs["reps"],
                    "lapses": srs["lapses"],
                    "motivo": "vencido",
                }
            )
            if mejor_vencido is None:
                mejor_vencido = cand
            elif cand["next_due"] < mejor_vencido["next_due"]:
                mejor_vencido = cand
            elif (
                cand["next_due"] == mejor_vencido["next_due"]
                and cand["id"] < mejor_vencido["id"]
            ):
                mejor_vencido = cand
        if mejor_vencido is not None:
            return mejor_vencido

        # 2) Nuevos: sin filas en intentos
        nuevo = conn.execute(
            """
            SELECT i.id, i.entidad, i.modulo_id, i.norma, i.articulo,
                   i.chunk_ids, i.enunciado, i.caso, i.dudoso, i.creado_en
            FROM items i
            WHERE i.entidad = %s
              AND i.modulo_id = %s
              AND i.dudoso = 0
              AND NOT EXISTS (
                    SELECT 1 FROM intentos t WHERE t.item_id = i.id
              )
            ORDER BY i.id ASC
            """,
            (entidad, modulo_id),
        ).fetchall()
        for row in nuevo:
            if int(row["id"]) in omitidos:
                continue
            out = dict(row)
            out["motivo"] = "nuevo"
            return out
        return None
    finally:
        if own:
            conn.close()


def listar_srs_modulo(
    *,
    entidad: str = "pgn",
    modulo_codigo: str = "esp_08",
) -> list[dict[str, Any]]:
    """Lista los calendarios de repaso cuyo último intento fue en ese módulo.

    Cómo: une `srs_estado` con `modulos` y filtra por el código. El orden es
    por `next_due` (los vacíos al final) y luego por número de artículo.
    Como `modulo_id` se actualiza en cada intento, aquí se ve el módulo que
    tocó el tema por última vez, no todos los módulos del artículo.

    Variables:
        entidad: organismo. Por defecto `pgn`.
        modulo_codigo: código del temario. Por defecto `esp_08`.

    Devuelve: filas con ease, intervalo, reps, lapses, next_due y artículo.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.entidad, s.modulo_id, m.codigo AS modulo_codigo,
                   s.norma, s.articulo, s.chunk_id, s.nivel,
                   s.ease, s.intervalo_dias, s.reps, s.lapses, s.next_due
            FROM srs_estado s
            JOIN modulos m ON m.id = s.modulo_id
            WHERE s.entidad = %s
              AND m.codigo = %s
            ORDER BY s.next_due NULLS LAST, s.articulo
            """,
            (entidad, modulo_codigo),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
