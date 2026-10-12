"""Cliente Chroma persistente en disco. Sin servidor aparte."""

from __future__ import annotations

from backend.config import settings


COLLECTION_NAME = "pgn_articulos"


def get_collection():
    """Abre (o crea) la colección Chroma guardada en disco.

    Cómo: asegura la carpeta de Chroma y abre un `PersistentClient` en esa ruta.
    El espacio de la colección es coseno: la distancia mide ángulo entre vectores,
    que es lo que luego se convierte en `Hit.score`. El nombre sale de
    `settings.chroma_collection` o, si viene vacío, de `pgn_articulos`.

    Variables:
        nombre: nombre de la colección.
        client: cliente Chroma apuntando a la carpeta local.

    Devuelve: la colección lista para `query` o `upsert`.
    """
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
