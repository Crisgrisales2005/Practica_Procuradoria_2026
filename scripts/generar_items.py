#!/usr/bin/env python3
"""Lote de ítems 5/2/0/0. Una llamada Gemini por query si el RAG supera el umbral."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import settings
from backend.db import init_db, listar_modulos
from backend.generation.batch import (
    LoteAbortado,
    cargar_queries,
    generar_lote,
)
from backend.generation.client import GeneracionError, ProveedorNoSoportado


def main() -> int:
    """Lanza un lote de generación de preguntas 5/2/0/0.

    Cómo: exige `--modulo` o `--all`. Comprueba limit, offset y k, inicializa
    la base y carga las queries del YAML. En corrida real exige proveedor
    `gemini` y `GOOGLE_API_KEY`. `generar_lote` hace el RAG, el umbral y las
    llamadas. Un aborto por cuota del día sale con código 3; por API caída o
    límite de minuto, con código 4.

    Variables:
        args.modulo: un código, o None si se pidió `--all`.
        args.all: recorre los 13 módulos en orden.
        args.limit: queries por módulo. Por defecto 20.
        args.offset: queries iniciales que se saltan.
        args.k: vecinos que pide el RAG. Por defecto 3.
        args.dry_run: solo muestra fragmentos, sin llamar a Gemini.
        args.entidad: organismo. Por defecto `pgn`.
        todos: módulos sembrados.
        elegidos: el módulo pedido o la lista completa.
        queries: mapa código → frases.
        resultado: acumulado del lote.

    Devuelve: 0 al terminar, 1 por error de generación o de archivos, 2 por
    argumentos o proveedor, 3 por cuota diaria, 4 por disponibilidad.
    """
    parser = argparse.ArgumentParser(
        description="Genera ítems de práctica (5/2/0/0) con RAG + Gemini."
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--modulo", help="Código, ej. esp_08")
    grupo.add_argument("--all", action="store_true", help="Los 13 módulos en orden")
    parser.add_argument("--limit", type=int, default=20, help="Queries por módulo")
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Salta las primeras N queries del módulo (continuar un lote).",
    )
    parser.add_argument("-k", type=int, default=3, help="Hits RAG a pedir")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo RAG + umbral + fragmentos; cero llamadas a Gemini.",
    )
    parser.add_argument("--entidad", default="pgn")
    args = parser.parse_args()

    if args.limit < 1:
        print("--limit debe ser ≥ 1", file=sys.stderr)
        return 2
    if args.offset < 0:
        print("--offset no puede ser negativo", file=sys.stderr)
        return 2
    if args.k < 1:
        print("-k debe ser ≥ 1", file=sys.stderr)
        return 2

    init_db()
    todos = listar_modulos(args.entidad)
    if not todos:
        print("No hay módulos sembrados. Ejecuta init_db.", file=sys.stderr)
        return 1

    if args.all:
        elegidos = todos
    else:
        elegidos = [m for m in todos if m["codigo"] == args.modulo]
        if not elegidos:
            print(f"Módulo desconocido: {args.modulo}", file=sys.stderr)
            return 2

    try:
        queries = cargar_queries()
    except FileNotFoundError as exc:
        print(f"No está el manifiesto de queries: {exc}", file=sys.stderr)
        return 1

    if not args.dry_run and settings.provider_label != "gemini":
        print(
            f"GENERATION_PROVIDER={settings.generation_provider}. "
            "En esta fase solo está implementado gemini; no se llama a nada.",
            file=sys.stderr,
        )
        return 2
    if not args.dry_run and not settings.has_google_api_key:
        print("Falta GOOGLE_API_KEY.", file=sys.stderr)
        return 2

    print(
        f"umbral RAG_MIN_SCORE={settings.rag_min_score}  "
        f"modelo={settings.gemini_model}  dry_run={args.dry_run}"
    )

    try:
        resultado = generar_lote(
            modulos=elegidos,
            queries_por_modulo=queries,
            limit=args.limit,
            k=args.k,
            entidad=args.entidad,
            dry_run=args.dry_run,
            offset=args.offset,
        )
    except ProveedorNoSoportado as exc:
        print(exc, file=sys.stderr)
        return 2
    except GeneracionError as exc:
        print(exc, file=sys.stderr)
        return 1
    except LoteAbortado as exc:
        if exc.resultado.detenido_por_cuota_diaria:
            return 3
        if exc.resultado.detenido_por_disponibilidad:
            return 4
        return 1
    except Exception as exc:
        print(f"No se pudo generar: {exc}", file=sys.stderr)
        return 1

    print(resultado.resumen())
    if resultado.ids_insertados:
        print("ids=" + ",".join(str(i) for i in resultado.ids_insertados))
    return 0


if __name__ == "__main__":
    sys.exit(main())
