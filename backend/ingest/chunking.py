"""Partir un decreto por artículo. Un chunk = un artículo."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.ingest.errors import IngestError

# Artículo 1. / Artículo 1°. / ARTÍCULO 1o. / ARTICULO 1
# No usar IGNORECASE en todo el patrón: [A-Z] con re.I también come la "o" de "1o."
_ARTICLE_HEADER = re.compile(
    r"(?m)(?:^|\n)\s*"
    r"(?i:art[ií]culo)\s+(?P<label>\d+[A-Z]?)\s*(?:o\.?|°|º)?\s*[.\-:]?"
)


@dataclass(frozen=True)
class ArticuloChunk:
    articulo: str
    texto: str
    norma: str


def partir_por_articulo(texto: str, norma: str) -> list[ArticuloChunk]:
    matches = list(_ARTICLE_HEADER.finditer(texto))
    if not matches:
        raise IngestError(
            "No se detectó ningún artículo en el texto. "
            "No se guarda un chunk único de todo el decreto."
        )

    chunks: list[ArticuloChunk] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        cuerpo = texto[start:end].strip()
        if not cuerpo:
            continue
        chunks.append(
            ArticuloChunk(
                articulo=match.group("label"),
                texto=cuerpo,
                norma=norma,
            )
        )

    if not chunks:
        raise IngestError(
            "No se detectó ningún artículo en el texto. "
            "No se guarda un chunk único de todo el decreto."
        )
    return chunks


def rotulos(chunks: list[ArticuloChunk]) -> list[str]:
    """Orden de detección, con repeticiones si el regex disparó dos veces."""
    return [c.articulo for c in chunks]
