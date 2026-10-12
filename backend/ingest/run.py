"""Orquesta manifiesto → PDF → chunks → Postgres."""

from __future__ import annotations

from pathlib import Path

from backend.config import settings
from backend.db.connection import init_db
from backend.ingest.chunking import partir_por_articulo
from backend.ingest.errors import IngestError
from backend.ingest.pdf import extraer_texto
from backend.ingest.persist import ResultadoIngesta, persistir_chunks, sha256_archivo


def _cargar_manifiesto(path: Path) -> dict:
    if not path.is_file():
        raise IngestError(f"No se encontró el manifiesto en: {path}")
    try:
        import yaml
    except ImportError as exc:
        raise IngestError(
            "Falta PyYAML. Instálalo en la imagen Docker (requirements.txt)."
        ) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise IngestError(f"El manifiesto no es un YAML de objeto: {path}")
    for campo in ("entidad", "archivo", "norma"):
        if not data.get(campo):
            raise IngestError(f"El manifiesto debe incluir '{campo}': {path}")
    if not data.get("modulo") and not data.get("modulos"):
        raise IngestError(f"El manifiesto debe incluir 'modulo' o 'modulos': {path}")
    return data


def _modulos_del_manifiesto(data: dict) -> list[str]:
    if data.get("modulos"):
        raw = data["modulos"]
        if not isinstance(raw, list) or not raw:
            raise IngestError("'modulos' debe ser una lista no vacía")
        return [str(m).strip() for m in raw]
    return [str(data["modulo"]).strip()]


def ingerir_desde_manifiesto(manifest_path: Path) -> ResultadoIngesta:
    init_db()
    data = _cargar_manifiesto(manifest_path)
    entidad = str(data["entidad"]).strip()
    archivo = str(data["archivo"]).strip()
    norma = str(data["norma"]).strip()
    modulos = _modulos_del_manifiesto(data)

    pdf_path = settings.documentos_dir / entidad / archivo
    if not pdf_path.is_file():
        raise IngestError(
            "No se encontró el PDF. Colócalo a mano en:\n"
            f"  {pdf_path}\n"
            "O corre: python scripts/descargar_normativa.py"
        )

    texto = extraer_texto(pdf_path)
    chunks = partir_por_articulo(texto, norma)
    digest = sha256_archivo(pdf_path)
    return persistir_chunks(
        entidad=entidad,
        nombre_archivo=archivo,
        sha256=digest,
        modulo_codigos=modulos,
        chunks=chunks,
    )
