#!/usr/bin/env python3
"""Ingesta CLI. No corre en la imagen de Render."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.ingest.errors import IngestError
from backend.ingest.run import ingerir_desde_manifiesto


def main() -> int:
    """Indexa en Postgres el PDF que indica un manifiesto.

    Cómo: resuelve la ruta del YAML (relativa a la raíz del repo si no es
    absoluta) y llama a `ingerir_desde_manifiesto`. Traduce la acción
    `ya_indexado`, `reindexado` o `insertado` a una frase e imprime cuántos
    artículos quedaron y sus números.

    Variables:
        args.manifest: ruta del YAML, obligatoria.
        manifest: ruta absoluta.
        resultado: `ResultadoIngesta`.
        etiquetas: nombre legible de cada acción.

    Devuelve: 0 si se guardó, 1 si el PDF, el manifiesto o el módulo fallaron.
    """
    parser = argparse.ArgumentParser(
        description="Indexa un PDF normativo en Postgres (por artículo)."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Ruta al YAML, ej. manifests/decreto_ley_262_2000.yaml",
    )
    args = parser.parse_args()
    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = ROOT / manifest

    try:
        resultado = ingerir_desde_manifiesto(manifest)
    except IngestError as exc:
        print(exc, file=sys.stderr)
        return 1

    etiquetas = {
        "ya_indexado": "Ya indexado (mismo archivo)",
        "reindexado": "Reindexado (mismo nombre, otro hash)",
        "insertado": "Indexado",
    }
    print(f"{etiquetas.get(resultado.accion, resultado.accion)}: {resultado.n_chunks} artículos.")
    print("Artículos detectados: " + ", ".join(resultado.articulos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
