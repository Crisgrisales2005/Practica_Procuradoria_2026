"""Única puerta de entrada a PostgreSQL (Supabase).

Pool con close_returns=True (psycopg_pool ≥ 3.3): conn.close() hace putconn.
Cold start del tier free: reintentos con backoff al abrir el pool / primer getconn.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from backend.config import settings

_DB_DIR = Path(__file__).resolve().parent

# Esperas entre intentos si el proyecto free está dormido (~30–60 s de wake).
_BACKOFF_SEGUNDOS = (5, 15, 30, 45)
_MAX_INTENTOS = 1 + len(_BACKOFF_SEGUNDOS)

_pool: Any = None


class DatabaseError(RuntimeError):
    """Fallo de conexión o de configuración de la base."""


def _raise_connect_error(ultimo: BaseException | None) -> None:
    detalle = str(ultimo or "")
    if "Network is unreachable" in detalle or "2600:" in detalle:
        raise DatabaseError(
            "No hay ruta IPv6 hasta Supabase (host db.…supabase.co suele ser solo IPv6). "
            "En el dashboard usa la connection string del pooler en Session mode "
            "(host …pooler.supabase.com, usuario postgres.<ref>) y pégala en DATABASE_URL. "
            f"Detalle: {ultimo}"
        ) from ultimo

    raise DatabaseError(
        "Supabase no responde (¿proyecto pausado en el tier gratuito?). "
        "Abre el dashboard del proyecto, espera a que despierte y reintenta. "
        f"Detalle: {ultimo}"
    ) from ultimo


def ensure_pool():
    """Crea (lazy) el ConnectionPool con close_returns=True. Idempotente."""
    global _pool
    if _pool is not None:
        return _pool

    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError as exc:
        raise DatabaseError(
            "Falta psycopg / psycopg_pool. Instálalos (requirements.txt / imagen Docker)."
        ) from exc

    if not settings.has_database_url:
        raise DatabaseError(
            "Falta DATABASE_URL. Copia la connection string de Supabase "
            "(Session mode) en .env — ver README."
        )

    pool = ConnectionPool(
        conninfo=settings.database_url,
        min_size=1,
        max_size=4,
        open=False,
        close_returns=True,
        kwargs={"row_factory": dict_row, "connect_timeout": 15},
    )

    ultimo: BaseException | None = None
    for intento in range(1, _MAX_INTENTOS + 1):
        try:
            pool.open(wait=True, timeout=30)
            _pool = pool
            return _pool
        except DatabaseError:
            raise
        except Exception as exc:
            ultimo = exc
            if intento >= _MAX_INTENTOS:
                break
            time.sleep(_BACKOFF_SEGUNDOS[intento - 1])

    try:
        pool.close()
    except Exception:
        pass
    _raise_connect_error(ultimo)


def get_connection():
    """Obtiene una conexión del pool. close() la devuelve (close_returns=True)."""
    pool = ensure_pool()
    ultimo: BaseException | None = None
    for intento in range(1, _MAX_INTENTOS + 1):
        try:
            return pool.getconn()
        except DatabaseError:
            raise
        except Exception as exc:
            ultimo = exc
            if intento >= _MAX_INTENTOS:
                break
            time.sleep(_BACKOFF_SEGUNDOS[intento - 1])
    _raise_connect_error(ultimo)


def _ejecutar_sql_archivo(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    for bloque in sql.split(";"):
        stmt = bloque.strip()
        if stmt:
            conn.execute(stmt)


def init_db() -> None:
    from backend.db.migrate_fase8 import migrar_fase8_esquema

    conn = get_connection()
    try:
        _ejecutar_sql_archivo(conn, _DB_DIR / "schema.sql")
        _ejecutar_sql_archivo(conn, _DB_DIR / "seed_modulos.sql")
        migrar_fase8_esquema(conn)
        conn.commit()
    finally:
        conn.close()


def listar_modulos(entidad: str = "pgn") -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, entidad, codigo, nombre, tipo, orden
            FROM modulos
            WHERE entidad = %s
            ORDER BY orden
            """,
            (entidad,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def listar_documentos(entidad: str = "pgn") -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, entidad, nombre_archivo, sha256, fecha_carga
            FROM documentos
            WHERE entidad = %s
            ORDER BY fecha_carga
            """,
            (entidad,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def contar_chunks(entidad: str = "pgn") -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE entidad = %s",
            (entidad,),
        ).fetchone()
        return int(row["n"]) if row else 0
    finally:
        conn.close()


def contar_items(entidad: str = "pgn") -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM items WHERE entidad = %s",
            (entidad,),
        ).fetchone()
        return int(row["n"]) if row else 0
    finally:
        conn.close()


def obtener_item(item_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT i.id, i.entidad, i.modulo_id, m.codigo AS modulo_codigo,
                   i.chunk_ids, i.norma, i.articulo, i.enunciado, i.caso,
                   i.opciones_json, i.matriz_json, i.dudoso, i.creado_en
            FROM items i
            JOIN modulos m ON m.id = i.modulo_id
            WHERE i.id = %s
            """,
            (item_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def listar_items_recientes(n: int = 5, entidad: str = "pgn") -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT i.id, i.entidad, i.modulo_id, m.codigo AS modulo_codigo,
                   i.chunk_ids, i.norma, i.articulo, i.enunciado, i.caso,
                   i.opciones_json, i.matriz_json, i.dudoso, i.creado_en
            FROM items i
            JOIN modulos m ON m.id = i.modulo_id
            WHERE i.entidad = %s
            ORDER BY i.id DESC
            LIMIT %s
            """,
            (entidad, n),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def contar_chunks_vectorizados(entidad: str = "pgn") -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM chunks
            WHERE entidad = %s
              AND chroma_id IS NOT NULL
              AND chroma_id != ''
            """,
            (entidad,),
        ).fetchone()
        return int(row["n"]) if row else 0
    finally:
        conn.close()
