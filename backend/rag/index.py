"""Leer chunks de Postgres y upsert en Chroma. ID = str(chunks.id) o id__modulo."""

from __future__ import annotations

from backend.db.connection import get_connection, init_db
from backend.rag.embed import embed_texts
from backend.rag.store import get_collection

BATCH_SIZE = 32


class IndexErrorRag(Exception):
    """No hay chunks para embeber o falló el índice."""


def _listar_chunks(entidad: str, solo_pendientes: bool) -> list[dict]:
    """Una fila por (chunk, módulo) vía chunk_modulos; fallback a chunks.modulo_id."""
    sql = """
        SELECT
            c.id,
            c.documento_id,
            cm.modulo_id,
            c.entidad,
            c.norma,
            c.articulo,
            c.texto,
            m.codigo AS modulo_codigo,
            c.chroma_id
        FROM chunks c
        JOIN chunk_modulos cm ON cm.chunk_id = c.id
        JOIN modulos m ON m.id = cm.modulo_id
        WHERE c.entidad = %s
    """
    params: list = [entidad]
    if solo_pendientes:
        sql += " AND (c.chroma_id IS NULL OR c.chroma_id = '')"
    sql += " ORDER BY c.id, m.codigo"

    conn = get_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _marcar_chroma_ids(chunk_ids: list[int]) -> None:
    if not chunk_ids:
        return
    conn = get_connection()
    try:
        for cid in chunk_ids:
            conn.execute(
                "UPDATE chunks SET chroma_id = %s WHERE id = %s",
                (str(cid), cid),
            )
        conn.commit()
    finally:
        conn.close()


def indexar_chunks(*, entidad: str = "pgn", reindex_all: bool = False) -> int:
    init_db()
    pendientes = _listar_chunks(entidad, solo_pendientes=not reindex_all)
    if not pendientes:
        todos = _listar_chunks(entidad, solo_pendientes=False)
        if not todos:
            raise IndexErrorRag(
                "No hay artículos en la base. Corre primero la ingesta del PDF "
                "(o la migración desde SQLite)."
            )
        return 0

    # Embeber cada chunk_id una sola vez; upsert una entrada Chroma por módulo.
    by_chunk: dict[int, list[dict]] = {}
    for row in pendientes:
        by_chunk.setdefault(int(row["id"]), []).append(row)

    collection = get_collection()
    indexados = 0
    chunk_ids = list(by_chunk.keys())
    for i in range(0, len(chunk_ids), BATCH_SIZE):
        lote_ids = chunk_ids[i : i + BATCH_SIZE]
        textos = [by_chunk[cid][0]["texto"] for cid in lote_ids]
        vectores = embed_texts(textos)
        ids: list[str] = []
        documentos: list[str] = []
        metadatas: list[dict] = []
        embeddings: list = []
        for cid, vec in zip(lote_ids, vectores):
            for row in by_chunk[cid]:
                chroma_id = f"{cid}__{row['modulo_codigo']}"
                ids.append(chroma_id)
                documentos.append(row["texto"])
                embeddings.append(vec)
                metadatas.append(
                    {
                        "chunk_id": cid,
                        "entidad": str(row["entidad"]),
                        "modulo_codigo": str(row["modulo_codigo"]),
                        "modulo_id": int(row["modulo_id"]),
                        "norma": str(row["norma"]),
                        "articulo": str(row["articulo"]),
                        "documento_id": int(row["documento_id"]),
                    }
                )
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documentos,
            metadatas=metadatas,
        )
        _marcar_chroma_ids(lote_ids)
        indexados += len(lote_ids)
    return indexados
