#!/usr/bin/env python3
"""Consulta RAG de comprobación. No genera ítems."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.rag.retrieve import recuperar


def main() -> int:
    parser = argparse.ArgumentParser(description="Recupera k artículos por módulo.")
    parser.add_argument("--modulo", required=True, help="Código, ej. esp_08")
    parser.add_argument("--query", required=True)
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--entidad", default="pgn")
    args = parser.parse_args()

    try:
        hits = recuperar(args.modulo, args.query, k=args.k, entidad=args.entidad)
    except Exception as exc:
        print(f"No se pudo consultar: {exc}", file=sys.stderr)
        return 1

    if not hits:
        print("sin resultados")
        return 0

    for i, hit in enumerate(hits, start=1):
        extracto = " ".join(hit.texto.split())
        if len(extracto) > 280:
            extracto = extracto[:277] + "..."
        print(f"{i}. art. {hit.articulo} | {hit.norma} | score={hit.score:.3f}")
        print(f"   {extracto}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
