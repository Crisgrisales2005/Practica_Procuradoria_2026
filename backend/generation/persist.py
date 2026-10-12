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
    """Hora actual en UTC, en texto ISO y sin microsegundos.

    Devuelve: la marca que se guarda en `items.creado_en`.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def modulo_id_por_codigo(codigo: str, entidad: str = "pgn") -> int | None:
    """Traduce un código de módulo al id de la tabla `modulos`.

    Variables:
        codigo: por ejemplo `esp_08`.
        entidad: organismo. Por defecto `pgn`.
        row: la fila encontrada.

    Devuelve: el id, o None si el código no está sembrado.
    """
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
    """Inserta una pregunta válida. Norma y artículo salen del RAG, no del modelo.

    Cómo: toma el primer hit como fuente de `norma`, `articulo` y `chunk_id`.
    Baraja el orden de las opciones y les asigna las letras A–D en ese nuevo
    orden, para que la respuesta óptima no quede siempre en la misma letra.
    `opciones_json` guarda letra, texto, puntaje y categoría. `matriz_json`
    añade la justificación, que la pantalla solo muestra después de responder.
    `dudoso` nace en 0.

    Variables:
        item: pregunta ya validada.
        hits: fragmentos usados. Hace falta al menos uno.
        entidad: organismo. Por defecto `pgn`.
        principal: el hit del que se copian norma y artículo.
        modulo_id: id del módulo en Postgres.
        mezcladas: opciones sin letra, en orden aleatorio.
        opciones: las cuatro opciones con letra nueva, sin justificación.
        matriz: las mismas, con justificación.
        chunk_ids: JSON con los ids de chunk de los hits.
        row: fila insertada, de la que se lee el id.

    Devuelve: el `items.id` nuevo.
    """
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
