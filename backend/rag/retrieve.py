"""Búsqueda por módulo. No genera texto ni llama a Gemini."""

from __future__ import annotations

from dataclasses import dataclass

from backend.rag.embed import embed_texts
from backend.rag.store import get_collection


@dataclass(frozen=True)
class Hit:
    """Un artículo recuperado por parecido con la pregunta.

    Variables:
        chunk_id: id del artículo en Postgres.
        chroma_id: id dentro de Chroma, con forma `chunkId__modulo`.
        modulo_codigo: módulo por el que se filtró la búsqueda.
        norma: nombre de la norma guardado al indexar.
        articulo: número de artículo.
        texto: texto completo del artículo.
        score: parecido de 0 a 1. Se calcula como `1 - distancia` del coseno.
    """
    chunk_id: int
    chroma_id: str
    modulo_codigo: str
    norma: str
    articulo: str
    texto: str
    score: float


def recuperar(
    modulo_codigo: str,
    query: str,
    k: int = 5,
    entidad: str = "pgn",
) -> list[Hit]:
    """Busca los artículos de un módulo más parecidos a una consulta.

    Cómo: convierte la consulta en un vector con el mismo modelo que el índice.
    Chroma compara ese vector solo contra metadatos `modulo_codigo` y `entidad`,
    y devuelve hasta `k` vecinos. La distancia de coseno se pasa a un puntaje
    `1 - distancia`, recortado a cero si quedara negativo. Una consulta vacía,
    un `k` menor que 1, una colección vacía o un fallo de Chroma devuelven lista
    vacía.

    Variables:
        modulo_codigo: código del temario, por ejemplo `esp_08`.
        query: texto de la pregunta o de la query de generación.
        k: máximo de artículos a pedir.
        entidad: organismo. Por defecto `pgn`.
        pregunta: `query` ya sin espacios.
        collection: colección Chroma en disco.
        vector: embedding de la pregunta.
        ids, docs, metas, dists: columnas paralelas que devuelve Chroma.
        distancia: distancia de coseno de ese vecino.
        hits: resultados ya armados, del más cercano al más lejano.

    Devuelve: lista de `Hit`, posiblemente vacía.
    """
    pregunta = (query or "").strip()
    if not pregunta or k < 1:
        return []

    collection = get_collection()
    if collection.count() == 0:
        return []

    vector = embed_texts([pregunta])[0]
    try:
        result = collection.query(
            query_embeddings=[vector],
            n_results=k,
            where={
                "$and": [
                    {"modulo_codigo": modulo_codigo},
                    {"entidad": entidad},
                ]
            },
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    if not ids:
        return []

    hits: list[Hit] = []
    for chroma_id, texto, meta, dist in zip(ids, docs, metas, dists):
        meta = meta or {}
        distancia = float(dist) if dist is not None else 1.0
        hits.append(
            Hit(
                chunk_id=int(meta.get("chunk_id") or chroma_id),
                chroma_id=str(chroma_id),
                modulo_codigo=str(meta.get("modulo_codigo") or modulo_codigo),
                norma=str(meta.get("norma") or ""),
                articulo=str(meta.get("articulo") or ""),
                texto=str(texto or ""),
                score=max(0.0, 1.0 - distancia),
            )
        )
    return hits
