#!/usr/bin/env python3
"""Muestra el siguiente ítem a practicar (vencidos > nuevos). Sin Gemini."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import init_db
from backend.srs import siguiente_item


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Elige el siguiente ítem (SRS): vencidos antes que nuevos."
    )
    parser.add_argument("--modulo", default="esp_08")
    parser.add_argument("--entidad", default="pgn")
    args = parser.parse_args()

    init_db()
    item = siguiente_item(entidad=args.entidad, modulo_codigo=args.modulo)
    if item is None:
        print("sin pendientes")
        return 0

    enunciado = " ".join((item.get("enunciado") or "").split())
    if len(enunciado) > 160:
        enunciado = enunciado[:157] + "..."
    print(f"motivo={item.get('motivo')} id={item['id']} art.={item['articulo']}")
    print(f"norma={item['norma']}")
    print(f"enunciado={enunciado}")
    if item.get("next_due"):
        print(
            f"srs: next_due={item['next_due']} ease={item.get('ease')} "
            f"reps={item.get('reps')} lapses={item.get('lapses')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
