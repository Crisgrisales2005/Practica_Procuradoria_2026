#!/usr/bin/env python3
"""Lee ítems persistidos para control de calidad humano. No llama a Gemini."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import init_db, listar_items_recientes, obtener_item


def _imprimir(row: dict) -> None:
    print(f"=== item id={row['id']} modulo={row['modulo_codigo']} ===")
    print(f"norma: {row['norma']}")
    print(f"articulo: {row['articulo']}")
    print(f"chunk_ids: {row['chunk_ids']}")
    print(f"creado_en: {row['creado_en']}")
    print()
    print("CASO")
    print(row["caso"])
    print()
    print("ENUNCIADO")
    print(row["enunciado"])
    print()
    try:
        matriz = json.loads(row["matriz_json"] or "[]")
    except json.JSONDecodeError:
        matriz = []
    if not matriz:
        try:
            matriz = json.loads(row["opciones_json"] or "[]")
        except json.JSONDecodeError:
            matriz = []
    for op in matriz:
        letra = op.get("letra", "?")
        puntaje = op.get("puntaje", "?")
        cat = op.get("categoria_distractor")
        print(f"{letra}  ({puntaje} pts)" + (f"  [{cat}]" if cat else ""))
        print(f"   {op.get('texto', '')}")
        just = op.get("justificacion")
        if just:
            print(f"   justificación: {just}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Imprime ítems del banco para revisión.")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--last", type=int, metavar="N", help="Últimos N ítems")
    grupo.add_argument("--id", type=int, dest="item_id", help="Un ítem por id")
    parser.add_argument("--entidad", default="pgn")
    args = parser.parse_args()

    init_db()

    if args.item_id is not None:
        row = obtener_item(args.item_id)
        if row is None:
            print(f"No existe el ítem {args.item_id}", file=sys.stderr)
            return 1
        _imprimir(row)
        return 0

    if args.last < 1:
        print("--last debe ser ≥ 1", file=sys.stderr)
        return 2
    rows = listar_items_recientes(args.last, entidad=args.entidad)
    if not rows:
        print("No hay ítems en el banco.")
        return 0
    # listar_items_recientes viene DESC; mostrar del más viejo al más nuevo del recorte
    for row in reversed(rows):
        _imprimir(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
