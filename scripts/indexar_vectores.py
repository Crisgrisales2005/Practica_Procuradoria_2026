#!/usr/bin/env python3
"""Embebe artículos de Postgres en Chroma. CLI admin; no corre en Render."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.rag.index import IndexErrorRag, indexar_chunks


def main() -> int:
    """Embebe en Chroma los artículos que ya están en Postgres.

    Cómo: llama a `indexar_chunks`. Sin `--reindex-all` solo procesa los que
    tienen `chroma_id` vacío. Con el flag, vuelve a calcular todos los vectores.

    Variables:
        args.reindex_all: True para reembeber todo.
        args.entidad: organismo. Por defecto `pgn`.
        n: cuántos artículos se indexaron.

    Devuelve: 0 si terminó, 1 si no hay artículos o falló el modelo.
    """
    parser = argparse.ArgumentParser(
        description="Indexa vectores de los artículos ya guardados en Postgres."
    )
    parser.add_argument(
        "--reindex-all",
        action="store_true",
        help="Vuelve a embeber todos los chunks, no solo los que tienen chroma_id vacío.",
    )
    parser.add_argument("--entidad", default="pgn")
    args = parser.parse_args()

    try:
        n = indexar_chunks(entidad=args.entidad, reindex_all=args.reindex_all)
    except IndexErrorRag as exc:
        print(exc, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"No se pudieron indexar vectores: {exc}", file=sys.stderr)
        return 1

    if n == 0:
        print("Nada pendiente: todos los artículos de esta entidad ya tienen chroma_id.")
    else:
        print(f"Indexados {n} artículos en Chroma.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
