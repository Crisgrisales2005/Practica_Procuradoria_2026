"""Partir un decreto por artículo. Un chunk = un artículo."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.ingest.errors import IngestError

# Artículo 1. / Artículo 1°. / ARTÍCULO 1o. / ARTICULO 1 / ARTÍCULO PRIMERO
# No usar IGNORECASE en todo el patrón: [A-Z] con re.I también come la "o" de "1o."
_ORDINAL = (
    r"PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[EÉ]PTIMO|OCTAVO|"
    r"NOVENO|D[EÉ]CIMO|UND[EÉ]CIMO|DUOD[EÉ]CIMO|DECIMOTERCERO|"
    r"DECIMOCUARTO|DECIMOQUINTO|DECIMOSEXTO|DECIMOS[EÉ]PTIMO|"
    r"DECIMOOCTAVO|DECIMONOVENO|VIG[EÉ]SIMO"
)
_ARTICLE_HEADER = re.compile(
    r"(?m)(?:^|\n)\s*"
    r"(?i:art[ií]culo)\s+(?P<label>\d+[A-Z]?|" + _ORDINAL + r")"
    r"\s*(?:o\.?|°|º)?\s*[.\-:]?",
    re.IGNORECASE,
)
# Manuales / protocolos sin «Artículo N»: secciones tipo «4. INTRODUCCIÓN».
_SECTION_HEADER = re.compile(
    r"(?m)(?:^|\n)\s*(?P<label>\d{1,3}(?:\.\d+)?)\.\s+"
    r"(?P<title>[A-ZÁÉÍÓÚÜÑ][^\n]{2,80})\s*(?=\n|$)"
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


def _chunks_desde_matches(
    texto: str, norma: str, matches: list[re.Match[str]], *, label_key: str = "label"
) -> list[ArticuloChunk]:
    chunks: list[ArticuloChunk] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        cuerpo = texto[start:end].strip()
        if not cuerpo:
            continue
        label = match.group(label_key)
        # Evitar filas del índice con puntos suspensivos.
        if cuerpo.count(".") > 40 and len(cuerpo) < 200:
            continue
        chunks.append(
            ArticuloChunk(articulo=str(label).strip(), texto=cuerpo, norma=norma)
        )
    return chunks


def partir_por_articulo(texto: str, norma: str) -> list[ArticuloChunk]:
    """Corta el texto de un decreto o ley en un trozo por artículo.

    Cómo: busca encabezados del estilo «Artículo 1», «ARTÍCULO 1o.»,
    «Artículo 1°» o «ARTÍCULO PRIMERO». Si no hay artículos numerados,
    intenta secciones tipo «4. INTRODUCCIÓN» (manuales / protocolos).
    No guarda el PDF entero como un solo chunk.

    Devuelve: los artículos/secciones en el orden en que aparecen en el PDF.
    """
    matches = list(_ARTICLE_HEADER.finditer(texto))
    chunks = _chunks_desde_matches(texto, norma, matches) if matches else []
    if chunks:
        return chunks

    sec_matches = [
        m
        for m in _SECTION_HEADER.finditer(texto)
        if "..." not in m.group(0) and "…" not in m.group(0)
    ]
    # Deduplicar TOC + cuerpo: quedarse con la última aparición de cada label.
    by_label: dict[str, re.Match[str]] = {}
    for m in sec_matches:
        by_label[m.group("label")] = m
    ordered = sorted(by_label.values(), key=lambda m: m.start())
    chunks = _chunks_desde_matches(texto, norma, ordered)
    if chunks:
        return chunks

    raise IngestError(
        "No se detectó ningún artículo ni sección en el texto. "
        "No se guarda un chunk único de todo el decreto."
    )


def rotulos(chunks: list[ArticuloChunk]) -> list[str]:
    """Lista los números de artículo en el orden en que se detectaron.

    Cómo: lee `articulo` de cada chunk. Si el regex disparó dos veces sobre el
    mismo número, ese número sale repetido: sirve para notar el fallo.

    Variables:
        chunks: artículos ya partidos.

    Devuelve: por ejemplo `["1", "2", "2", "3"]`.
    """
    return [c.articulo for c in chunks]
