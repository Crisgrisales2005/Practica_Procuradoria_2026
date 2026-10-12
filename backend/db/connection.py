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

# Esperas opcionales (scripts admin / CLI) si Supabase está dormido.
_BACKOFF_SEGUNDOS = (5, 15, 30, 45)
_MAX_INTENTOS = 1 + len(_BACKOFF_SEGUNDOS)

# Pool: espera máxima al pedir una conexión (evita colgar el proceso).
_POOL_TIMEOUT_S = 15.0
_POOL_OPEN_TIMEOUT_S = 15.0

_pool: Any = None
_pool_opened: bool = False


class DatabaseError(RuntimeError):
    """La base no está configurada o Supabase no aceptó la conexión.

    El mensaje va dirigido a quien usa la app: qué revisar en `.env` o en el dashboard.
    """


def _raise_connect_error(ultimo: BaseException | None) -> None:
    """Convierte el último fallo de red en un `DatabaseError` con pista de arreglo.

    Cómo: mira el texto de la excepción. Si aparece «Network is unreachable» o una
    dirección IPv6 (`2600:`), el host de Supabase es el directo (`db.…`) y no el
    pooler. En cualquier otro caso asume que el proyecto gratuito está dormido.

    Variables:
        ultimo: la excepción que quedó tras agotar los reintentos. Puede ser None.

    No devuelve: siempre lanza `DatabaseError`.
    """
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
    """Crea el ConnectionPool (lazy) sin bloquear el arranque del proceso.

    No abre conexiones a Supabase aquí: eso ocurre en get_connection / open_pool.
    Así /api/healthz puede responder aunque la DB esté dormida.
    """
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

    _pool = ConnectionPool(
        conninfo=settings.database_url,
        min_size=1,
        max_size=4,
        open=False,
        timeout=_POOL_TIMEOUT_S,
        close_returns=True,
        kwargs={"row_factory": dict_row, "connect_timeout": 15},
    )
    return _pool


def open_pool(*, wait: bool = True, timeout: float | None = None) -> Any:
    """Abre el pool si aún no está abierto. Timeout acotado (no backoff largo)."""
    global _pool_opened
    pool = ensure_pool()
    if _pool_opened:
        return pool
    t = _POOL_OPEN_TIMEOUT_S if timeout is None else timeout
    try:
        pool.open(wait=wait, timeout=t)
        _pool_opened = True
        return pool
    except Exception as exc:
        _raise_connect_error(exc)


def get_connection(*, retry_backoff: bool = False):
    """Pide una conexión del pool. close() la devuelve (close_returns=True).

    Por defecto un solo intento con timeout del pool (web). Con
    retry_backoff=True reintenta con esperas largas (scripts admin / CLI).
    """
    pool = ensure_pool()
    intentos = _MAX_INTENTOS if retry_backoff else 1
    ultimo: BaseException | None = None
    for intento in range(1, intentos + 1):
        try:
            if not _pool_opened:
                open_pool(wait=True, timeout=_POOL_OPEN_TIMEOUT_S)
            return pool.getconn()
        except DatabaseError:
            raise
        except Exception as exc:
            ultimo = exc
            if intento >= intentos:
                break
            time.sleep(_BACKOFF_SEGUNDOS[intento - 1])
    _raise_connect_error(ultimo)


def _ejecutar_sql_archivo(conn, path: Path) -> None:
    """Ejecuta un archivo `.sql` sentencia por sentencia.

    Cómo: lee el archivo completo y lo parte por `;`. Cada trozo con texto se
    manda a Postgres. No hace `commit`: eso lo decide quien llamó.

    Variables:
        conn: conexión abierta del pool.
        path: ruta del archivo, por ejemplo `schema.sql` o `seed_modulos.sql`.
        sql: texto completo del archivo.
        bloque: cada pedazo entre punto y coma.
        stmt: ese pedazo ya sin espacios; se salta si quedó vacío.
    """
    sql = path.read_text(encoding="utf-8")
    for bloque in sql.split(";"):
        stmt = bloque.strip()
        if stmt:
            conn.execute(stmt)


def init_db() -> None:
    """Deja la base lista: tablas, los 13 módulos y el ajuste de la fase 8.

    Cómo: en una sola conexión corre `schema.sql` (CREATE IF NOT EXISTS),
    luego `seed_modulos.sql` y por último `migrar_fase8_esquema` (tabla
    `chunk_modulos` y la clave única del repaso). Si todo sale bien, confirma
    con `commit` y devuelve la conexión al pool.

    Variables:
        conn: conexión prestada del pool durante toda la inicialización.
    """
    from backend.db.migrate_fase8 import migrar_fase8_esquema

    conn = get_connection()
    try:
        _ejecutar_sql_archivo(conn, _DB_DIR / "schema.sql")
        _ejecutar_sql_archivo(conn, _DB_DIR / "seed_modulos.sql")
        migrar_fase8_esquema(conn)
        conn.commit()
    finally:
        conn.close()


def listar_modulos(entidad: str = "pgn", *, conn=None) -> list[dict]:
    """Lista los módulos de una entidad. Si `conn` se pasa, no abre otra."""
    own = conn is None
    if own:
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
        if own:
            conn.close()


def listar_documentos(entidad: str = "pgn") -> list[dict]:
    """Lista los PDF ya registrados en la tabla `documentos`.

    Cómo: filtra por entidad y ordena por `fecha_carga`.

    Variables:
        entidad: organismo. Por defecto `pgn`.

    Devuelve: diccionarios con `id`, `entidad`, `nombre_archivo`, `sha256` y `fecha_carga`.
    """
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
    """Cuenta los artículos (chunks) guardados para una entidad.

    Variables:
        entidad: organismo. Por defecto `pgn`.
        row: la fila `COUNT(*)`; `n` es el número.

    Devuelve: cuántos artículos hay en `chunks`. Cero si la consulta no trae fila.
    """
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
    """Cuenta las preguntas del banco (`items`) de una entidad.

    Variables:
        entidad: organismo. Por defecto `pgn`.

    Devuelve: cuántos ítems hay. Cero si la consulta no trae fila.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM items WHERE entidad = %s",
            (entidad,),
        ).fetchone()
        return int(row["n"]) if row else 0
    finally:
        conn.close()


def obtener_item(item_id: int, *, conn=None) -> dict | None:
    """Trae una pregunta completa. Si `conn` se pasa, no abre otra."""
    own = conn is None
    if own:
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
        if own:
            conn.close()


def listar_items_recientes(n: int = 5, entidad: str = "pgn") -> list[dict]:
    """Trae las últimas preguntas creadas, de la más nueva a la más vieja.

    Variables:
        n: cuántas filas como máximo. Por defecto 5.
        entidad: organismo. Por defecto `pgn`.

    Devuelve: la misma forma que `obtener_item`, en una lista.
    """
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
    """Cuenta artículos que ya tienen vector en Chroma.

    Cómo: un chunk está vectorizado cuando `chroma_id` tiene texto. El índice
    guarda ahí el id de Postgres en texto al terminar de embeber.

    Variables:
        entidad: organismo. Por defecto `pgn`.

    Devuelve: cuántos artículos ya se pueden buscar por parecido.
    """
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
