"""Embeddings locales en español. El modelo se carga una vez por proceso."""

from __future__ import annotations

import os

from backend.config import settings

_model = None


def _ensure_cache_env() -> None:
    cache = settings.ensure_hf_cache_dir()
    os.environ.setdefault("HF_HOME", str(cache))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(cache))


def get_model():
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
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return [v.tolist() for v in vectors]
