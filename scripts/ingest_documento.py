#!/usr/bin/env python3
"""Ingesta CLI. No se ejecuta al abrir Streamlit."""

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
