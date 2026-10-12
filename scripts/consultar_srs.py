#!/usr/bin/env python3
"""Lista el estado SRS de un módulo. Sin Gemini."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import init_db
from backend.srs import listar_srs_modulo


def main() -> int:
    parser = argparse.ArgumentParser(description="Consulta srs_estado por módulo.")
    parser.add_argument("--modulo", default="esp_08")
    parser.add_argument("--entidad", default="pgn")
    args = parser.parse_args()

    init_db()
    filas = listar_srs_modulo(entidad=args.entidad, modulo_codigo=args.modulo)
    if not filas:
        print("sin filas srs_estado")
        return 0

    for s in filas:
        print(
            f"art.{s['articulo']:<5} chunk={s['chunk_id']:<4} "
            f"ease={float(s['ease']):.2f} int={s['intervalo_dias']} "
            f"reps={s['reps']} lapses={s['lapses']} "
            f"next_due={s['next_due']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
