#!/usr/bin/env python3
"""Simula responder un ítem (SRS). No llama a Gemini."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import init_db
from backend.srs import SrsError, marcar_dudoso, registrar_intento


def main() -> int:
    """Registra un intento o cambia la marca de dudoso desde la terminal.

    Cómo: exige `--item-id` y exactamente una de estas acciones: `--puntaje`
    0, 2 o 5, `--marcar-dudoso` o `--quitar-dudoso`. Inicializa la base y llama
    a `registrar_intento` o a `marcar_dudoso`. Imprime el antes y el después
    del calendario SRS.

    Variables:
        args.item_id: pregunta sobre la que se actúa.
        args.puntaje: 5, 2 o 0, si se está respondiendo.
        args.marcar_dudoso / args.quitar_dudoso: cambian `items.dudoso`.
        res: diccionario que devuelve el servicio SRS.
        u: unidad de repaso (norma, artículo, chunk, nivel).
        a / d: estado SRS antes y después.

    Devuelve: 0 si se guardó, 1 si el ítem o la base fallaron.
    """
    parser = argparse.ArgumentParser(
        description="Registra un intento 5/2/0 o marca un ítem como dudoso."
    )
    parser.add_argument("--item-id", type=int, required=True)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--puntaje", type=int, choices=[0, 2, 5])
    grupo.add_argument(
        "--marcar-dudoso",
        action="store_true",
        help="Marca el ítem como dudoso (se excluye de la práctica).",
    )
    grupo.add_argument(
        "--quitar-dudoso",
        action="store_true",
        help="Quita la marca de dudoso.",
    )
    args = parser.parse_args()

    init_db()
    try:
        if args.marcar_dudoso or args.quitar_dudoso:
            res = marcar_dudoso(args.item_id, dudoso=bool(args.marcar_dudoso))
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        res = registrar_intento(args.item_id, args.puntaje)
    except SrsError as exc:
        print(exc, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"intento_id={res['intento_id']} item={res['item_id']} puntaje={res['puntaje']}")
    u = res["unidad"]
    print(
        f"unidad: modulo_id={u['modulo_id']} norma={u['norma']} "
        f"art.={u['articulo']} chunk_id={u['chunk_id']} nivel={u['nivel']}"
    )
    a, d = res["srs_antes"], res["srs_despues"]
    print(
        f"SRS antes:  ease={a['ease']:.2f} int={a['intervalo_dias']} "
        f"reps={a['reps']} lapses={a['lapses']} next_due={a['next_due']}"
    )
    print(
        f"SRS después: ease={d['ease']:.2f} int={d['intervalo_dias']} "
        f"reps={d['reps']} lapses={d['lapses']} next_due={d['next_due']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
