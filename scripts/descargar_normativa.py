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
    """Lee la lista fija de descargas oficiales.

    Cómo: el YAML debe tener `items`. `entidad` sale del archivo o, si falta, `pgn`.

    Variables:
        path: ruta de `manifests/descargas_normativa.yaml`.
        data: documento YAML.
        entidad: carpeta destino bajo `documentos_entidades`.
        items: lista de `{archivo, url, tipo}`.

    Devuelve: la entidad y esa lista.
    """
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
    """Quita basura que algunos sitios .gov.co ponen antes de la cabecera PDF.

    Cómo: busca los bytes `%PDF-`. Si están, devuelve el archivo desde ahí.
    Si no aparecen, devuelve los bytes tal cual para que `_es_pdf` los rechace.

    Variables:
        data: cuerpo HTTP completo.
        i: posición de `%PDF-`.

    Devuelve: el PDF limpio, o el cuerpo original.
    """
    i = data.find(b"%PDF-")
    if i < 0:
        return data
    return data[i:]


def _es_pdf(data: bytes, content_type: str) -> bool:
    """Comprueba que el cuerpo sea un PDF por su cabecera mágica.

    Cómo: mira los primeros 5 bytes. Tienen que ser `%PDF-`. El Content-Type
    `pdf` u `octet-stream` acompaña, pero la cabecera manda: sin `%PDF-` no es PDF.

    Variables:
        data: cuerpo ya normalizado.
        content_type: cabecera HTTP Content-Type.
        ct: ese tipo en minúsculas.
        head: los primeros 5 bytes.

    Devuelve: True si empieza por `%PDF-`.
    """
    ct = (content_type or "").lower()
    head = data[:5]
    if "pdf" in ct and head == b"%PDF-":
        return True
    if "octet-stream" in ct and head == b"%PDF-":
        return True
    return head == b"%PDF-"


def _es_html(data: bytes, content_type: str) -> bool:
    """Comprueba que el cuerpo sea HTML.

    Cómo: acepta Content-Type `html` o `text/plain`, o un inicio `<!doctype html`
    o `<html` en los primeros 200 bytes, ignorando espacios.

    Variables:
        data: cuerpo HTTP.
        content_type: cabecera Content-Type.
        ct: ese tipo en minúsculas.
        head: inicio del cuerpo, en minúsculas y sin espacios a la izquierda.

    Devuelve: True si parece HTML.
    """
    ct = (content_type or "").lower()
    if "html" in ct or "text/plain" in ct:
        return True
    head = data[:200].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _descargar(url: str, destino: Path, tipo: str, *, insecure_ssl: bool) -> None:
    """Baja una URL oficial y la guarda solo si el tipo coincide.

    Cómo: pide la URL con un User-Agent fijo y 120 segundos de espera. Exige
    HTTP 200 y un cuerpo con bytes. Si `tipo` es `pdf`, recorta hasta `%PDF-`
    y valida la cabecera. Si es `html`, valida que sea HTML. Crea la carpeta
    destino y escribe el archivo.

    Variables:
        url: dirección oficial del manifiesto.
        destino: ruta local del archivo.
        tipo: `pdf` o `html`.
        insecure_ssl: True no verifica el certificado. Algunos .gov.co traen
            la cadena incompleta.
        req: petición con el User-Agent del proyecto.
        ctx: contexto SSL verificado o sin verificar.
        status: código HTTP.
        content_type: tipo declarado por el servidor.
        data: cuerpo, ya recortado si era PDF.
    """
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
    """Descarga cada archivo del manifiesto y se salta los que ya existen.

    Cómo: lee el YAML, arma `documentos_entidades/<entidad>/` y recorre `items`.
    Un destino que ya tiene tamaño mayor que cero se cuenta como OK sin volver
    a bajarlo. Un fallo de red o de tipo se imprime y sigue con el siguiente.

    Variables:
        args.manifest: ruta del YAML. Por defecto `manifests/descargas_normativa.yaml`.
        args.insecure_ssl: pasa el modo sin verificación de certificado.
        manifest: ruta absoluta.
        entidad / items: lo que devolvió `_cargar_items`.
        dest_root: carpeta de esa entidad.
        ok / fail: conteos.
        archivo / url / tipo / destino: campos de cada ítem y su ruta local.

    Devuelve: 0 si no hubo fallos, 1 si alguno falló.
    """
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
