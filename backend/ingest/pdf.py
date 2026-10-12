"""Extracción de texto de PDFs oficiales. Sin OCR y sin APIs."""

from __future__ import annotations

import re
from pathlib import Path

from backend.ingest.errors import IngestError

_MIN_CHARS = 500


def extraer_texto(pdf_path: Path) -> str:
    if not pdf_path.is_file():
        raise IngestError(f"No se encontró el PDF en: {pdf_path}")

    try:
        import pdfplumber
    except ImportError as exc:
        raise IngestError(
            "Falta pdfplumber. Instálalo en la imagen Docker (requirements.txt)."
        ) from exc

    paginas: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                paginas.append(page.extract_text() or "")
    except Exception as exc:  # pdfplumber/pdfminer
        raise IngestError(f"No se pudo leer el PDF ({pdf_path}): {exc}") from exc

    texto = "\n".join(paginas)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()

    if len(texto) < _MIN_CHARS:
        raise IngestError(
            "este PDF no tiene capa de texto; el OCR no entra en el MVP"
        )
    return texto
