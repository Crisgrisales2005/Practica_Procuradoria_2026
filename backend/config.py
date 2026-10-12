"""Lee variables de entorno. No llama a ninguna API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # el contenedor sí lo instala; en el host puede faltar
    load_dotenv = None

# Repo root (…/Procuradoria), tanto en local como en el contenedor.
_ROOT = Path(__file__).resolve().parent.parent
if load_dotenv is not None:
    load_dotenv(_ROOT / ".env")


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        return ""
    return value.strip()


def _env_float(name: str, default: float) -> float:
    raw = _env(name, str(default))
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return default


def _data_root() -> Path:
    data_root = Path(os.getenv("DATA_ROOT", "/data"))
    if not data_root.exists():
        data_root = _ROOT / "data"
    return data_root


@dataclass(frozen=True)
class Settings:
    google_api_key: str
    database_url: str
    generation_provider: str
    ollama_base_url: str
    gemini_model: str
    embedding_model: str
    chroma_collection: str
    rag_min_score: float
    # Solo para generation.log y lectura del app.db legado en la migración.
    sqlite_dir: Path
    chroma_dir: Path
    documentos_dir: Path
    hf_cache_dir: Path

    @property
    def sqlite_path(self) -> Path:
        return self.sqlite_dir / "app.db"

    @property
    def chroma_path(self) -> Path:
        return self.chroma_dir

    def ensure_sqlite_dir(self) -> Path:
        self.sqlite_dir.mkdir(parents=True, exist_ok=True)
        return self.sqlite_dir

    def ensure_chroma_dir(self) -> Path:
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        return self.chroma_dir

    def ensure_hf_cache_dir(self) -> Path:
        self.hf_cache_dir.mkdir(parents=True, exist_ok=True)
        return self.hf_cache_dir

    @property
    def has_google_api_key(self) -> bool:
        return bool(self.google_api_key)

    @property
    def has_database_url(self) -> bool:
        return bool(self.database_url)

    @property
    def provider_label(self) -> str:
        return self.generation_provider.lower() or "gemini"


def load_settings() -> Settings:
    data_root = _data_root()

    documentos = Path(os.getenv("DOCUMENTOS_DIR", "/data/documentos_entidades"))
    if not documentos.exists():
        documentos = _ROOT / "documentos_entidades"

    hf_cache = Path(os.getenv("HF_HOME", "/data/hf_cache"))
    if not hf_cache.exists() and not str(hf_cache).startswith("/data"):
        hf_cache.mkdir(parents=True, exist_ok=True)
    if not hf_cache.exists():
        hf_cache = data_root / "hf_cache"

    chroma_dir = data_root / "chroma" if data_root.name != "chroma" else data_root
    sqlite_dir = data_root / "sqlite" if data_root.name != "sqlite" else data_root

    return Settings(
        google_api_key=_env("GOOGLE_API_KEY"),
        database_url=_env("DATABASE_URL"),
        generation_provider=_env("GENERATION_PROVIDER", "gemini") or "gemini",
        ollama_base_url=_env(
            "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
        )
        or "http://host.docker.internal:11434",
        gemini_model=_env("GEMINI_MODEL", "gemini-3.8-flash")
        or "gemini-3.8-flash",
        embedding_model=_env(
            "EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2"
        )
        or "paraphrase-multilingual-mpnet-base-v2",
        chroma_collection=_env("CHROMA_COLLECTION", "pgn_articulos")
        or "pgn_articulos",
        rag_min_score=_env_float("RAG_MIN_SCORE", 0.35),
        sqlite_dir=sqlite_dir,
        chroma_dir=chroma_dir,
        documentos_dir=documentos,
        hf_cache_dir=hf_cache,
    )


settings = load_settings()
