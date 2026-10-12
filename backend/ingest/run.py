"""Orquesta manifiesto → PDF → chunks → Postgres."""

from __future__ import annotations

from pathlib import Path

from backend.config import settings
from backend.db.connection import init_db
from backend.ingest.chunking import partir_por_articulo
from backend.ingest.errors import IngestError
from backend.ingest.pdf import extraer_texto
from backend.ingest.persist import ResultadoIngesta, persistir_chunks, sha256_archivo


def _cargar_manifiesto(path: Path) -> dict:
    """Lee el YAML que dice qué PDF ingerir y a qué módulos pertenece.

    Cómo: exige que el archivo exista y que el YAML sea un objeto con
    `entidad`, `archivo` y `norma`, más `modulo` o `modulos`.

    Variables:
        path: ruta del manifiesto, por ejemplo `manifests/ley_594_2000.yaml`.
        data: diccionario ya parseado.

    Devuelve: ese diccionario.
    Lanza: `IngestError` si falta el archivo, PyYAML o algún campo.
    """
    if not path.is_file():
        raise IngestError(f"No se encontró el manifiesto en: {path}")
    try:
        import yaml
    except ImportError as exc:
        raise IngestError(
            "Falta PyYAML. Instálalo en la imagen Docker (requirements.txt)."
        ) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise IngestError(f"El manifiesto no es un YAML de objeto: {path}")
    for campo in ("entidad", "archivo", "norma"):
        if not data.get(campo):
            raise IngestError(f"El manifiesto debe incluir '{campo}': {path}")
    if not data.get("modulo") and not data.get("modulos"):
        raise IngestError(f"El manifiesto debe incluir 'modulo' o 'modulos': {path}")
    return data


def _modulos_del_manifiesto(data: dict) -> list[str]:
    """Saca la lista de códigos de módulo, venga uno o varios.

    Cómo: si el YAML trae `modulos`, usa esa lista. Si trae un solo `modulo`,
    lo envuelve en una lista de un elemento.

    Variables:
        data: manifiesto ya validado por `_cargar_manifiesto`.
        raw: el valor crudo de `modulos` antes de limpiar espacios.

    Devuelve: códigos como `["esp_06", "com_13"]`.
    """
    if data.get("modulos"):
        raw = data["modulos"]
        if not isinstance(raw, list) or not raw:
            raise IngestError("'modulos' debe ser una lista no vacía")
        return [str(m).strip() for m in raw]
    return [str(data["modulo"]).strip()]


def ingerir_desde_manifiesto(manifest_path: Path) -> ResultadoIngesta:
    """Pasa un PDF oficial a artículos guardados en Postgres.

    Cómo: inicializa la base, lee el manifiesto, busca el PDF en
    `documentos_dir/<entidad>/<archivo>`, extrae el texto, lo parte por
    artículo, calcula el SHA-256 y llama a `persistir_chunks`.

    Variables:
        manifest_path: ruta del YAML.
        data: contenido del manifiesto.
        entidad: organismo, por ejemplo `pgn`.
        archivo: nombre del PDF dentro de la carpeta de la entidad.
        norma: nombre de la norma que se copia a cada artículo.
        modulos: códigos de módulo a los que se enlaza el documento.
        pdf_path: ruta real del archivo en disco.
        texto: texto plano del PDF.
        chunks: un `ArticuloChunk` por artículo detectado.
        digest: hash SHA-256 del archivo, para saber si ya se indexó.

    Devuelve: `ResultadoIngesta` con la acción (`insertado`, `reindexado` o
    `ya_indexado`), el id del documento y los artículos.
    """
    init_db()
    data = _cargar_manifiesto(manifest_path)
    entidad = str(data["entidad"]).strip()
    archivo = str(data["archivo"]).strip()
    norma = str(data["norma"]).strip()
    modulos = _modulos_del_manifiesto(data)

    pdf_path = settings.documentos_dir / entidad / archivo
    if not pdf_path.is_file():
        raise IngestError(
            "No se encontró el PDF. Colócalo a mano en:\n"
            f"  {pdf_path}\n"
            "O corre: python scripts/descargar_normativa.py"
        )

    texto = extraer_texto(pdf_path)
    chunks = partir_por_articulo(texto, norma)
    digest = sha256_archivo(pdf_path)
    return persistir_chunks(
        entidad=entidad,
        nombre_archivo=archivo,
        sha256=digest,
        modulo_codigos=modulos,
        chunks=chunks,
    )
