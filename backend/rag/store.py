"""Cliente Chroma persistente en disco. Sin servidor aparte."""

from __future__ import annotations

from backend.config import settings


COLLECTION_NAME = "pgn_articulos"


def get_collection():
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "Falta chromadb. Instálalo (requirements.txt / imagen Docker)."
        ) from exc

    settings.ensure_chroma_dir()
    nombre = settings.chroma_collection or COLLECTION_NAME
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    return client.get_or_create_collection(
        name=nombre,
        metadata={"hnsw:space": "cosine"},
    )
