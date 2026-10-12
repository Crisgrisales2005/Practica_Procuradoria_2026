#!/usr/bin/env python3
"""Reinicia el progreso de práctica: intentos, SRS y presentaciones → 0.

No borra el banco de preguntas (items) ni documentos/chunks.
Requiere confirmación explícita --confirm.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.connection import get_connection


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Borra intentos / srs_estado / presentaciones_consumidas."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Obligatorio. Sin esto solo muestra conteos.",
    )
    parser.add_argument(
        "--entidad",
        default="pgn",
        help="Filtra items/intentos por entidad (default pgn).",
    )
    args = parser.parse_args()

    conn = get_connection(retry_backoff=True)
    try:
        n_intentos = conn.execute(
            """
            SELECT COUNT(*)::int AS n FROM intentos t
            JOIN items i ON i.id = t.item_id
            WHERE i.entidad = %s
            """,
            (args.entidad,),
        ).fetchone()["n"]
        n_srs = conn.execute(
            "SELECT COUNT(*)::int AS n FROM srs_estado WHERE entidad = %s",
            (args.entidad,),
        ).fetchone()["n"]
        try:
            n_pres = conn.execute(
                "SELECT COUNT(*)::int AS n FROM presentaciones_consumidas"
            ).fetchone()["n"]
        except Exception:
            n_pres = 0
            conn.rollback()

        print(
            f"entidad={args.entidad}: intentos={n_intentos} "
            f"srs_estado={n_srs} presentaciones={n_pres}"
        )
        if not args.confirm:
            print("Dry-run. Para borrar: python scripts/reset_practica.py --confirm")
            return 0

        # Orden: presentaciones (FK a intentos) → intentos → srs
        try:
            conn.execute("DELETE FROM presentaciones_consumidas")
        except Exception as exc:
            conn.rollback()
            print(f"(presentaciones_consumidas omitida: {exc})", file=sys.stderr)

        conn.execute(
            """
            DELETE FROM intentos t
            USING items i
            WHERE t.item_id = i.id AND i.entidad = %s
            """,
            (args.entidad,),
        )
        conn.execute(
            "DELETE FROM srs_estado WHERE entidad = %s",
            (args.entidad,),
        )
        # Quitar marca dudoso para que vuelvan al banco activo
        conn.execute(
            "UPDATE items SET dudoso = 0 WHERE entidad = %s AND dudoso <> 0",
            (args.entidad,),
        )
        conn.commit()
        print("Listo: progreso a 0. El banco de preguntas (items) se conserva.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
