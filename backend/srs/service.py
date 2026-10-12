"""Registro de intentos, SRS y marca de dudoso. Solo vía get_connection()."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from backend.db.connection import get_connection
from backend.srs.sm2 import NIVEL_CASO, EstadoSrs, aplicar_puntaje, iso_utc, utc_now


class SrsError(ValueError):
    """Error de dominio SRS / intentos."""


def _chunk_id_desde_item(chunk_ids_raw: str | None) -> int:
    # asume 1 solo chunk_id; revisar si algún día se soportan ítems multi-fragmento
    try:
        ids = json.loads(chunk_ids_raw or "[]")
    except json.JSONDecodeError as exc:
        raise SrsError("chunk_ids del ítem no es JSON válido") from exc
    if not isinstance(ids, list) or not ids:
        raise SrsError("el ítem no tiene chunk_ids; no se puede resolver la unidad SRS")
    return int(ids[0])


def resolver_unidad_desde_item(item: dict[str, Any]) -> dict[str, Any]:
    """Unidad de repaso: (entidad, norma, articulo, chunk_id, nivel).

    modulo_id del ítem se guarda en srs_estado solo como referencia informativa
    (último módulo que disparó el intento); no forma parte de la UNIQUE (Fase 8).
    """
    return {
        "entidad": item["entidad"],
        "modulo_id": int(item["modulo_id"]),
        "norma": item["norma"],
        "articulo": item["articulo"],
        "chunk_id": _chunk_id_desde_item(item.get("chunk_ids")),
        "nivel": NIVEL_CASO,
    }


def _cargar_item(conn, item_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, entidad, modulo_id, chunk_ids, norma, articulo,
               enunciado, caso, dudoso, creado_en
        FROM items
        WHERE id = %s
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise SrsError(f"No existe el ítem {item_id}")
    return dict(row)


def _leer_srs(conn, unidad: dict[str, Any]) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, entidad, modulo_id, norma, articulo, chunk_id, nivel,
               ease, intervalo_dias, reps, lapses, next_due
        FROM srs_estado
        WHERE entidad = %s
          AND norma = %s
          AND articulo = %s
          AND chunk_id = %s
          AND nivel = %s
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


def _estado_desde_fila(fila: dict[str, Any] | None) -> EstadoSrs:
    if fila is None:
        return EstadoSrs()
    return EstadoSrs(
        ease=float(fila["ease"]),
        intervalo_dias=int(fila["intervalo_dias"]),
        reps=int(fila["reps"]),
        lapses=int(fila["lapses"]),
        next_due=fila.get("next_due"),
    )


def registrar_intento(item_id: int, puntaje: int) -> dict[str, Any]:
    if puntaje not in (0, 2, 5):
        raise SrsError("puntaje debe ser 0, 2 o 5")

    ahora = utc_now()
    conn = get_connection()
    try:
        item = _cargar_item(conn, item_id)
        unidad = resolver_unidad_desde_item(item)
        antes_fila = _leer_srs(conn, unidad)
        antes = _estado_desde_fila(antes_fila)
        despues = aplicar_puntaje(antes, puntaje, ahora=ahora)

        row = conn.execute(
            """
            INSERT INTO intentos (item_id, puntaje, respondido_en)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (item_id, puntaje, iso_utc(ahora)),
        ).fetchone()
        intento_id = int(row["id"])

        if antes_fila is None:
            conn.execute(
                """
                INSERT INTO srs_estado (
                    entidad, modulo_id, norma, articulo, chunk_id, nivel,
                    ease, intervalo_dias, reps, lapses, next_due
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    unidad["entidad"],
                    unidad["modulo_id"],
                    unidad["norma"],
                    unidad["articulo"],
                    unidad["chunk_id"],
                    unidad["nivel"],
                    despues.ease,
                    despues.intervalo_dias,
                    despues.reps,
                    despues.lapses,
                    despues.next_due,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE srs_estado
                SET ease = %s,
                    intervalo_dias = %s,
                    reps = %s,
                    lapses = %s,
                    next_due = %s,
                    modulo_id = %s
                WHERE id = %s
                """,
                (
                    despues.ease,
                    despues.intervalo_dias,
                    despues.reps,
                    despues.lapses,
                    despues.next_due,
                    unidad["modulo_id"],
                    int(antes_fila["id"]),
                ),
            )

        conn.commit()
        return {
            "intento_id": intento_id,
            "item_id": item_id,
            "puntaje": puntaje,
            "unidad": unidad,
            "srs_antes": asdict(antes),
            "srs_despues": asdict(despues),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def marcar_dudoso(item_id: int, dudoso: bool = True) -> dict[str, Any]:
    conn = get_connection()
    try:
        item = _cargar_item(conn, item_id)
        flag = 1 if dudoso else 0
        conn.execute(
            "UPDATE items SET dudoso = %s WHERE id = %s",
            (flag, item_id),
        )
        conn.commit()
        return {"item_id": item_id, "dudoso": flag, "antes": int(item.get("dudoso") or 0)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
