"""Leer chunks de Postgres y upsert en Chroma. ID = str(chunks.id) o id__modulo."""

from __future__ import annotations

from backend.db.connection import get_connection, init_db
from backend.rag.embed import embed_texts
from backend.rag.store import get_collection

BATCH_SIZE = 32


class IndexErrorRag(Exception):
    """No hay artículos en Postgres para embeber, o el índice no pudo arrancar."""


def _listar_chunks(entidad: str, solo_pendientes: bool) -> list[dict]:
    """Lista artículos unidos a cada módulo al que pertenecen.

    Cómo: parte de `chunk_modulos`, así un mismo artículo (Ley 594) sale una
    vez por módulo. Si `solo_pendientes` es verdadero, se queda con los que
    todavía tienen `chroma_id` vacío.

    Variables:
        entidad: organismo, por ejemplo `pgn`.
        solo_pendientes: True para indexar solo lo nuevo; False para traer todos.
        sql: la consulta, a la que se le añade el filtro y el ORDER BY.
        params: valores de la consulta; el primero es `entidad`.

    Devuelve: filas con texto, norma, artículo, código de módulo y `chroma_id`.
    """
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
    """Anota en Postgres que esos artículos ya tienen vector.

    Cómo: guarda `str(id)` en `chunks.chroma_id`. El id real dentro de Chroma
    es `id__modulo`, pero esta columna solo marca «ya indexado» para no
    reembeber el mismo texto en la próxima corrida.

    Variables:
        chunk_ids: ids de Postgres del lote que acaba de subirse a Chroma.
        cid: un id de ese lote.
    """
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
    """Convierte artículos de Postgres en vectores y los guarda en Chroma.

    Cómo: inicializa la base y lista los chunks pendientes (o todos, si
    `reindex_all`). Agrupa las filas por `chunk_id` para embeber el texto una
    sola vez aunque el artículo pertenezca a varios módulos. Cada lote de 32
    textos se vectoriza y se sube con un id `chunkId__moduloCodigo` por módulo,
    reutilizando el mismo vector. Después marca esos ids en Postgres.

    Variables:
        entidad: organismo. Por defecto `pgn`.
        reindex_all: True vuelve a embeber aunque `chroma_id` ya tenga valor.
        pendientes: filas (chunk, módulo) que entran en esta corrida.
        todos: todos los artículos, solo para distinguir «no hay nada» de «ya está hecho».
        by_chunk: mapa de id de chunk a sus filas (una por módulo).
        collection: colección Chroma.
        indexados: cuántos chunks (no entradas de módulo) se procesaron.
        lote_ids: hasta 32 ids de este lote.
        textos: un texto por chunk, tomado de la primera fila del grupo.
        vectores: embeddings, en el mismo orden que `lote_ids`.
        chroma_id: id compuesto `id__codigo` para que el mismo artículo viva
            en varios módulos sin pisarse.

    Devuelve: cuántos artículos se embebieron. Cero si ya estaban todos marcados.
    Lanza: `IndexErrorRag` si Postgres no tiene ningún artículo.
    """
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
