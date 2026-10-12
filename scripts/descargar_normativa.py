#!/usr/bin/env python3
"""Descarga URLs oficiales del manifiesto estático. Sin descubrimiento ni scraping."""

from __future__ import annotations

import argparse
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UA = "ProcuradoriaPrep/1.0 (estudio local; fuentes oficiales verificadas)"


def _cargar_items(path: Path) -> tuple[str, list[dict]]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "items" not in data:
        raise SystemExit(f"Manifiesto inválido: {path}")
    entidad = str(data.get("entidad") or "pgn")
    items = data["items"]
    if not isinstance(items, list):
        raise SystemExit("items debe ser una lista")
    return entidad, items


def _normalizar_pdf(data: bytes) -> bytes:
    """Algunos .gov.co anteponen whitespace/BOM antes de %PDF-."""
    i = data.find(b"%PDF-")
    if i < 0:
        return data
    return data[i:]


def _es_pdf(data: bytes, content_type: str) -> bool:
    ct = (content_type or "").lower()
    head = data[:5]
    if "pdf" in ct and head == b"%PDF-":
        return True
    if "octet-stream" in ct and head == b"%PDF-":
        return True
    return head == b"%PDF-"


def _es_html(data: bytes, content_type: str) -> bool:
    ct = (content_type or "").lower()
    if "html" in ct or "text/plain" in ct:
        return True
    head = data[:200].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _descargar(url: str, destino: Path, tipo: str, *, insecure_ssl: bool) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl._create_unverified_context() if insecure_ssl else ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
        status = getattr(resp, "status", None) or resp.getcode()
        if int(status) != 200:
            raise RuntimeError(f"HTTP {status}")
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
    if not data:
        raise RuntimeError("cuerpo vacío")
    if tipo == "pdf":
        data = _normalizar_pdf(data)
        if not _es_pdf(data, content_type):
            raise RuntimeError(
                f"Content-Type/magic no es PDF (Content-Type={content_type!r}, "
                f"inicio={data[:20]!r})"
            )
    elif tipo == "html" and not _es_html(data, content_type):
        raise RuntimeError(
            f"Content-Type/magic no es HTML (Content-Type={content_type!r})"
        )
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Descarga normativa desde manifests/descargas_normativa.yaml"
    )
    parser.add_argument(
        "--manifest",
        default="manifests/descargas_normativa.yaml",
        help="Ruta al YAML de descargas",
    )
    parser.add_argument(
        "--insecure-ssl",
        action="store_true",
        help="No verificar cadena SSL (algunos sitios .gov.co tienen CA incompleta).",
    )
    args = parser.parse_args()
    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = ROOT / manifest

    entidad, items = _cargar_items(manifest)
    dest_root = ROOT / "documentos_entidades" / entidad
    ok = 0
    fail = 0
    for item in items:
        archivo = str(item["archivo"])
        url = str(item["url"])
        tipo = str(item.get("tipo") or "pdf").lower()
        destino = dest_root / archivo
        if destino.is_file() and destino.stat().st_size > 0:
            print(f"SKIP {archivo} (ya existe)")
            ok += 1
            continue
        try:
            _descargar(url, destino, tipo, insecure_ssl=args.insecure_ssl)
            print(f"OK  {archivo}  ({destino.stat().st_size} bytes)")
            ok += 1
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, OSError) as exc:
            print(f"FAIL {archivo}\n  url={url}\n  error={exc}", file=sys.stderr)
            fail += 1

    print(f"descargas OK={ok} FAIL={fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
