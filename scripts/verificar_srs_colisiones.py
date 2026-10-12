#!/usr/bin/env python3
"""Verificación previa obligatoria antes de migrar UNIQUE srs_estado (Fase 8)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.connection import get_connection, init_db
from backend.db.migrate_fase8 import verificar_colisiones_srs


def main() -> int:
    # Solo lectura de colisiones; init_db aplicará migración si aún no corre.
    # Aquí abrimos conexión y verificamos ANTES si el caller quiere solo check:
    conn = get_connection()
    try:
        # Asegurar tabla existe
        conn.execute("SELECT 1 FROM srs_estado LIMIT 1")
        info = verificar_colisiones_srs(conn)
    finally:
        conn.close()

    print(f"n_srs={info['n_srs']}")
    print(f"grupos_colision={len(info['colisiones'])}")
    for g in info["colisiones"]:
        print(g)
    if info["colisiones"]:
        print("HAY COLISIONES: consolidar antes de cambiar UNIQUE.", file=sys.stderr)
        return 2
    print("OK: sin colisiones para UNIQUE (entidad, norma, articulo, chunk_id, nivel)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
