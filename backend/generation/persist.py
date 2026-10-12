"""INSERT de ítems válidos. norma/artículo salen del hit RAG, no del modelo."""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone

from backend.db.connection import get_connection
from backend.generation.validate import ItemLLM
from backend.rag.retrieve import Hit

_LETRAS = ("A", "B", "C", "D")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def modulo_id_por_codigo(codigo: str, entidad: str = "pgn") -> int | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM modulos WHERE entidad = %s AND codigo = %s",
            (entidad, codigo),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def guardar_item(
    item: ItemLLM,
    hits: list[Hit],
    entidad: str = "pgn",
) -> int:
    if not hits:
        raise ValueError("no hay hits RAG para copiar norma/artículo")
    principal = hits[0]
    modulo_id = modulo_id_por_codigo(item.modulo_codigo, entidad)
    if modulo_id is None:
        raise ValueError(f"módulo desconocido: {item.modulo_codigo}")

    # Barajar posición de la óptima: no confiar en que el modelo varíe la letra.
    mezcladas = [
        {
            "texto": op.texto,
            "puntaje": op.puntaje,
            "categoria_distractor": op.categoria_distractor,
            "justificacion": op.justificacion,
        }
        for op in item.opciones
    ]
    random.shuffle(mezcladas)
    opciones = [
        {
            "letra": letra,
            "texto": op["texto"],
            "puntaje": op["puntaje"],
            "categoria_distractor": op["categoria_distractor"],
        }
        for letra, op in zip(_LETRAS, mezcladas)
    ]
    matriz = [
        {
            **opciones[i],
            "justificacion": mezcladas[i]["justificacion"],
        }
        for i in range(4)
    ]
    chunk_ids = json.dumps([h.chunk_id for h in hits], ensure_ascii=False)

    conn = get_connection()
    try:
        row = conn.execute(
            """
            INSERT INTO items (
                entidad, modulo_id, parent_item_id, chunk_ids,
                norma, articulo, enunciado, caso,
                opciones_json, matriz_json, dudoso, creado_en
            ) VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, 0, %s)
            RETURNING id
            """,
            (
                entidad,
                modulo_id,
                chunk_ids,
                principal.norma,
                principal.articulo,
                item.enunciado,
                item.caso,
                json.dumps(opciones, ensure_ascii=False),
                json.dumps(matriz, ensure_ascii=False),
                _utc_now(),
            ),
        ).fetchone()
        conn.commit()
        return int(row["id"])
    finally:
        conn.close()
