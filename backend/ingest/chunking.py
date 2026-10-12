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
    """Un artículo ya recortado, listo para guardarse como un chunk.

    Variables:
        articulo: número tal como lo vio el regex, por ejemplo `7` o `12A`.
        texto: desde el encabezado «Artículo N» hasta el siguiente encabezado.
        norma: nombre de la norma, copiado del manifiesto (igual para todos).
    """
    articulo: str
    texto: str
    norma: str


def partir_por_articulo(texto: str, norma: str) -> list[ArticuloChunk]:
    """Corta el texto de un decreto o ley en un trozo por artículo.

    Cómo: busca encabezados del estilo «Artículo 1», «ARTÍCULO 1o.» o
    «Artículo 1°». Cada coincidencia abre un trozo que termina donde empieza
    el siguiente encabezado (o al final del texto). Un trozo vacío se descarta.
    Si no aparece ningún encabezado, no guarda el decreto entero como un solo
    chunk: lanza error para no indexar basura.

    Variables:
        texto: texto plano ya extraído del PDF.
        norma: nombre que se copia a cada `ArticuloChunk`.
        matches: todas las coincidencias del encabezado, en orden.
        chunks: lista que se va armando.
        start / end: índices de carácter de este artículo dentro de `texto`.
        cuerpo: el recorte ya sin espacios sobrantes.
        label: el número capturado por el regex (`label`).

    Devuelve: los artículos en el orden en que aparecen en el PDF.
    """
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
    """Lista los números de artículo en el orden en que se detectaron.

    Cómo: lee `articulo` de cada chunk. Si el regex disparó dos veces sobre el
    mismo número, ese número sale repetido: sirve para notar el fallo.

    Variables:
        chunks: artículos ya partidos.

    Devuelve: por ejemplo `["1", "2", "2", "3"]`.
    """
    return [c.articulo for c in chunks]
