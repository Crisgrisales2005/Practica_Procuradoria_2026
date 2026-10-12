"""Hash + documentos + chunks + chunk_modulos. Solo vía get_connection(); close explícito."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.db.connection import get_connection
from backend.ingest.chunking import ArticuloChunk
from backend.ingest.errors import IngestError


@dataclass(frozen=True)
class ResultadoIngesta:
    """Qué pasó al guardar un PDF en Postgres.

    Variables:
        accion: `ya_indexado` (mismo hash), `reindexado` (mismo nombre, otro
            archivo) o `insertado` (documento nuevo).
        documento_id: id de la fila en `documentos`.
        n_chunks: cuántos artículos quedaron asociados a ese documento.
        articulos: números de artículo, en el orden guardado.
    """
    accion: str  # ya_indexado | reindexado | insertado
    documento_id: int
    n_chunks: int
    articulos: list[str]


def sha256_archivo(path: Path) -> str:
    """Calcula el SHA-256 del archivo leyéndolo de a 1 MB.

    Cómo: no carga el PDF entero en memoria. Actualiza el hash con cada bloque
    hasta que `read` devuelve bytes vacíos.

    Variables:
        path: ruta del PDF.
        digest: acumulador del hash.
        bloque: el trozo de hasta 1 MB recién leído.

    Devuelve: el hash en hexadecimal, que se guarda en `documentos.sha256`.
    """
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _resolver_modulo_id(conn, entidad: str, codigo: str) -> int:
    """Traduce un código de módulo (`esp_08`) al id numérico de la tabla `modulos`.

    Variables:
        conn: conexión abierta.
        entidad: organismo, por ejemplo `pgn`.
        codigo: código del temario.
        row: la fila encontrada, o None.

    Devuelve: `modulos.id`.
    Lanza: `IngestError` si el código no está en la semilla.
    """
    row = conn.execute(
        "SELECT id FROM modulos WHERE entidad = %s AND codigo = %s",
        (entidad, codigo),
    ).fetchone()
    if row is None:
        raise IngestError(
            f"No existe el módulo '{codigo}' para entidad '{entidad}'. "
            "Revisa el manifiesto y la semilla de módulos."
        )
    return int(row["id"])


def persistir_chunks(
    *,
    entidad: str,
    nombre_archivo: str,
    sha256: str,
    modulo_codigos: list[str],
    chunks: list[ArticuloChunk],
) -> ResultadoIngesta:
    """Guarda los artículos y decide si el PDF es nuevo, repetido o reemplazo.

    Cómo, dentro de una transacción:
    1. Resuelve cada código de módulo a su id. El primero (`canonico`) es el
       que se copia a `chunks.modulo_id`; todos se enlazan en `chunk_modulos`.
    2. Si ya hay un documento con el mismo SHA-256, no reescribe los artículos:
       solo asegura los enlaces de módulo y devuelve `ya_indexado`.
    3. Si el nombre de archivo ya existe pero el hash cambió, borra los chunks
       viejos, actualiza hash y fecha, inserta los nuevos y devuelve `reindexado`.
    4. Si no hay coincidencia, inserta el documento y los artículos (`insertado`).
    Un error hace `rollback`. Al final la conexión vuelve al pool.

    Variables:
        entidad: organismo dueño del PDF.
        nombre_archivo: nombre del archivo, sin carpetas.
        sha256: hash calculado por `sha256_archivo`.
        modulo_codigos: códigos del manifiesto, al menos uno.
        chunks: artículos ya partidos.
        ahora: fecha UTC de la carga, en texto ISO.
        articulos: números de artículo de esta corrida.
        modulo_ids: ids numéricos, en el mismo orden que los códigos.
        canonico: primer módulo; queda en la columna histórica `chunks.modulo_id`.
        mismo_hash / mismo_nombre: fila previa, si existe.
        doc_id: id del documento nuevo o reutilizado.
    """
    if not modulo_codigos:
        raise IngestError("se requiere al menos un módulo en el manifiesto")
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    articulos = [c.articulo for c in chunks]

    conn = get_connection()
    try:
        modulo_ids = [_resolver_modulo_id(conn, entidad, c) for c in modulo_codigos]
        canonico = modulo_ids[0]

        mismo_hash = conn.execute(
            """
            SELECT id FROM documentos
            WHERE entidad = %s AND sha256 = %s
            """,
            (entidad, sha256),
        ).fetchone()
        if mismo_hash is not None:
            doc_id = int(mismo_hash["id"])
            # Asegurar enlaces multi-módulo aunque el PDF ya estuviera indexado.
            _asegurar_chunk_modulos(conn, doc_id, modulo_ids)
            conn.commit()
            rows = conn.execute(
                """
                SELECT articulo FROM chunks
                WHERE documento_id = %s
                ORDER BY id
                """,
                (doc_id,),
            ).fetchall()
            return ResultadoIngesta(
                accion="ya_indexado",
                documento_id=doc_id,
                n_chunks=len(rows),
                articulos=[str(r["articulo"]) for r in rows],
            )

        mismo_nombre = conn.execute(
            """
            SELECT id FROM documentos
            WHERE entidad = %s AND nombre_archivo = %s
            """,
            (entidad, nombre_archivo),
        ).fetchone()

        if mismo_nombre is not None:
            doc_id = int(mismo_nombre["id"])
            conn.execute("DELETE FROM chunks WHERE documento_id = %s", (doc_id,))
            conn.execute(
                """
                UPDATE documentos
                SET sha256 = %s, fecha_carga = %s
                WHERE id = %s
                """,
                (sha256, ahora, doc_id),
            )
            _insertar_chunks(conn, doc_id, entidad, canonico, chunks, modulo_ids)
            conn.commit()
            return ResultadoIngesta(
                accion="reindexado",
                documento_id=doc_id,
                n_chunks=len(chunks),
                articulos=articulos,
            )

        row = conn.execute(
            """
            INSERT INTO documentos (entidad, nombre_archivo, sha256, fecha_carga)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (entidad, nombre_archivo, sha256, ahora),
        ).fetchone()
        doc_id = int(row["id"])
        _insertar_chunks(conn, doc_id, entidad, canonico, chunks, modulo_ids)
        conn.commit()
        return ResultadoIngesta(
            accion="insertado",
            documento_id=doc_id,
            n_chunks=len(chunks),
            articulos=articulos,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _asegurar_chunk_modulos(conn, documento_id: int, modulo_ids: list[int]) -> None:
    """Enlaza los artículos de un documento ya guardado con los módulos pedidos.

    Cómo: lista los `chunks.id` de ese documento e inserta cada par
    (chunk, módulo) en `chunk_modulos`. `ON CONFLICT DO NOTHING` evita duplicar
    la clave primaria si el enlace ya estaba.

    Variables:
        conn: conexión abierta, dentro de la transacción de `persistir_chunks`.
        documento_id: id en `documentos`.
        modulo_ids: módulos a los que debe pertenecer cada artículo.
        cid: id de un chunk.
        mid: id de un módulo.
    """
    chunk_ids = conn.execute(
        "SELECT id FROM chunks WHERE documento_id = %s",
        (documento_id,),
    ).fetchall()
    for row in chunk_ids:
        cid = int(row["id"])
        for mid in modulo_ids:
            conn.execute(
                """
                INSERT INTO chunk_modulos (chunk_id, modulo_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (cid, mid),
            )


def _insertar_chunks(
    conn,
    documento_id: int,
    entidad: str,
    modulo_canonico: int,
    chunks: list[ArticuloChunk],
    modulo_ids: list[int],
) -> None:
    """Inserta cada artículo y sus enlaces de módulo.

    Cómo: una fila en `chunks` por artículo, con `chroma_id` vacío (el vector
    se calcula después). Luego una fila en `chunk_modulos` por cada módulo.

    Variables:
        conn: conexión abierta.
        documento_id: documento padre.
        entidad: se copia a cada chunk para filtrar búsquedas.
        modulo_canonico: módulo que queda en `chunks.modulo_id`.
        chunks: artículos a insertar.
        modulo_ids: todos los módulos del manifiesto, incluido el canónico.
        cid: id recién generado del chunk.
        mid: cada módulo al que se enlaza ese chunk.
    """
    for chunk in chunks:
        row = conn.execute(
            """
            INSERT INTO chunks (
                documento_id, modulo_id, entidad, norma, articulo, texto, chroma_id
            ) VALUES (%s, %s, %s, %s, %s, %s, NULL)
            RETURNING id
            """,
            (
                documento_id,
                modulo_canonico,
                entidad,
                chunk.norma,
                chunk.articulo,
                chunk.texto,
            ),
        ).fetchone()
        cid = int(row["id"])
        for mid in modulo_ids:
            conn.execute(
                """
                INSERT INTO chunk_modulos (chunk_id, modulo_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (cid, mid),
            )
