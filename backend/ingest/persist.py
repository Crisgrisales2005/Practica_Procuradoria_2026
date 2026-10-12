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
    accion: str  # ya_indexado | reindexado | insertado
    documento_id: int
    n_chunks: int
    articulos: list[str]


def sha256_archivo(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _resolver_modulo_id(conn, entidad: str, codigo: str) -> int:
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
