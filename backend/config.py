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
    """Lee una variable de entorno y le quita espacios.

    Cómo: consulta el entorno del proceso (el `.env` ya se cargó al importar
    este módulo). Si la variable no existe y no hay valor de respaldo, devuelve
    texto vacío para que el resto del programa pueda preguntar «¿está configurada?»
    con un simple `if`.

    Variables:
        name: nombre exacto, por ejemplo `GOOGLE_API_KEY` o `DATABASE_URL`.
        default: texto que se usa cuando la variable no está definida.

    Devuelve: el valor sin espacios al inicio ni al final.
    """
    value = os.getenv(name, default)
    if value is None:
        return ""
    return value.strip()


def _env_float(name: str, default: float) -> float:
    """Lee una variable de entorno y la convierte a número decimal.

    Cómo: toma el texto con `_env` y cambia la coma por punto, para aceptar
    tanto `0.35` como `0,35`. Si el texto no es un número, se queda con `default`.

    Variables:
        name: nombre de la variable, por ejemplo `RAG_MIN_SCORE`.
        default: número de respaldo si falta la variable o no se puede leer.

    Devuelve: el número leído, o `default`.
    """
    raw = _env(name, str(default))
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return default


def _data_root() -> Path:
    """Elige la carpeta donde viven Chroma, logs admin y la caché.

    Cómo: prueba `DATA_ROOT` (en Docker suele ser `/data`). Si esa carpeta no
    existe en esta máquina, usa `<repo>/data`.

    Devuelve: la ruta que sí existe, o la del repositorio si `/data` no está.
    """
    data_root = Path(os.getenv("DATA_ROOT", "/data"))
    if not data_root.exists():
        data_root = _ROOT / "data"
    return data_root


@dataclass(frozen=True)
class Settings:
    """Configuración ya leída. El objeto queda congelado: no se reasigna campo a campo."""

    google_api_key: str
    database_url: str
    generation_provider: str
    ollama_base_url: str
    gemini_model: str
    embedding_model: str
    chroma_collection: str
    rag_min_score: float
    logs_dir: Path
    chroma_dir: Path
    documentos_dir: Path
    hf_cache_dir: Path
    app_password: str
    session_secret: str
    session_https_only: bool

    @property
    def chroma_path(self) -> Path:
        """Carpeta del índice Chroma. Es el mismo valor que `chroma_dir`."""
        return self.chroma_dir

    def ensure_logs_dir(self) -> Path:
        """Crea `logs_dir` (y sus padres) si todavía no existe.

        Devuelve: esa misma carpeta, ya creada.
        """
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        return self.logs_dir

    def ensure_chroma_dir(self) -> Path:
        """Crea `chroma_dir` si todavía no existe.

        Devuelve: esa misma carpeta, ya creada.
        """
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        return self.chroma_dir

    def ensure_hf_cache_dir(self) -> Path:
        """Crea la caché de Hugging Face si todavía no existe.

        Devuelve: `hf_cache_dir`, ya creada.
        """
        self.hf_cache_dir.mkdir(parents=True, exist_ok=True)
        return self.hf_cache_dir

    @property
    def has_google_api_key(self) -> bool:
        """True cuando `google_api_key` tiene algún carácter."""
        return bool(self.google_api_key)

    @property
    def has_database_url(self) -> bool:
        """True cuando `database_url` tiene algún carácter."""
        return bool(self.database_url)

    @property
    def provider_label(self) -> str:
        """Nombre del proveedor en minúsculas. Si viene vacío, usa `gemini`."""
        return self.generation_provider.lower() or "gemini"


def load_settings() -> Settings:
    """Arma un `Settings` leyendo el entorno y eligiendo carpetas reales.

    Cómo: parte de `_data_root()`. Los documentos se buscan primero en
    `DOCUMENTOS_DIR` y, si esa ruta no existe, en `<repo>/documentos_entidades`.
    La caché del modelo sigue la misma idea con `HF_HOME`. Chroma y logs
    cuelgan de la raíz de datos, salvo que esa raíz ya se llame `chroma` o `logs`.

    Devuelve: el objeto de configuración que el resto del proyecto importa como `settings`.
    """
    data_root = _data_root()

    documentos = Path(os.getenv("DOCUMENTOS_DIR", "/data/documentos_entidades"))
    if not documentos.exists():
        documentos = _ROOT / "documentos_entidades"

    # No crear carpetas al importar: el servicio web no necesita Chroma/HF.
    hf_cache = Path(os.getenv("HF_HOME", "/data/hf_cache"))
    if not hf_cache.exists():
        hf_cache = data_root / "hf_cache"

    chroma_dir = data_root / "chroma" if data_root.name != "chroma" else data_root
    logs_dir = data_root / "logs" if data_root.name != "logs" else data_root

    https_raw = _env("SESSION_HTTPS_ONLY", "").lower()
    if https_raw in ("1", "true", "yes"):
        session_https_only = True
    elif https_raw in ("0", "false", "no"):
        session_https_only = False
    else:
        # Por defecto: Secure solo si parece producción (Render pone RENDER=true).
        session_https_only = bool(_env("RENDER") or _env("FORCE_HTTPS"))

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
        logs_dir=logs_dir,
        chroma_dir=chroma_dir,
        documentos_dir=documentos,
        hf_cache_dir=hf_cache,
        app_password=_env("APP_PASSWORD"),
        session_secret=_env("SESSION_SECRET") or _env("APP_PASSWORD") or "dev-only-change-me",
        session_https_only=session_https_only,
    )


settings = load_settings()
