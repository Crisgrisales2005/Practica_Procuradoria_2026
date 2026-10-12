"""Embeddings locales en español. El modelo se carga una vez por proceso."""

from __future__ import annotations

import os

from backend.config import settings

_model = None


def _ensure_cache_env() -> None:
    """Apunta Hugging Face y sentence-transformers a la caché del proyecto.

    Cómo: crea la carpeta si falta y define `HF_HOME` y
    `SENTENCE_TRANSFORMERS_HOME` solo si el proceso todavía no las trae.
    Así el modelo de ~1 GB se descarga una vez en `data/hf_cache`.

    Variables:
        cache: ruta ya creada de `settings.hf_cache_dir`.
    """
    cache = settings.ensure_hf_cache_dir()
    os.environ.setdefault("HF_HOME", str(cache))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(cache))


def get_model():
    """Carga el modelo de embeddings una sola vez por proceso.

    Cómo: si `_model` ya está en memoria, lo devuelve. Si no, fija la caché,
    construye `SentenceTransformer` con `settings.embedding_model` y guarda
    la instancia en la variable global.

    Variables:
        _model: None hasta la primera carga; después, el modelo listo.

    Devuelve: el modelo con el que se llama a `encode`.
    """
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Falta sentence-transformers. Instálalo (requirements.txt / imagen Docker)."
        ) from exc

    _ensure_cache_env()
    _model = SentenceTransformer(settings.embedding_model, cache_folder=str(settings.hf_cache_dir))
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Convierte textos en vectores numéricos con el modelo local.

    Cómo: una lista vacía no carga el modelo. El resto pasa por `encode` y cada
    vector numpy se vuelve una lista de floats para Chroma.

    Variables:
        texts: frases o artículos a embeber, en orden.
        model: modelo ya cargado.
        vectors: matriz numpy, una fila por texto.

    Devuelve: una lista de vectores, en el mismo orden que `texts`.
    """
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return [v.tolist() for v in vectors]
