"""Búsqueda por módulo. No genera texto ni llama a Gemini."""

from __future__ import annotations

from dataclasses import dataclass

from backend.rag.embed import embed_texts
from backend.rag.store import get_collection


@dataclass(frozen=True)
class Hit:
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
