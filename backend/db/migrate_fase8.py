"""Migración Fase 8: chunk_modulos + UNIQUE srs sin modulo_id.

Obligatorio: verificar colisiones en srs_estado antes de alterar el constraint.
"""

from __future__ import annotations

from typing import Any


def verificar_colisiones_srs(conn) -> dict[str, Any]:
    """Busca unidades de repaso duplicadas en `srs_estado`.

    Cómo: agrupa por entidad, norma, artículo, chunk y nivel. Un grupo con más
    de una fila es una colisión: el mismo tema tendría dos calendarios de
    repaso, y la clave única nueva no podría crearse.

    Variables:
        conn: conexión Postgres ya abierta. Esta función no hace commit.
        n: cuántas filas hay en total en `srs_estado`.
        grupos: solo los grupos cuyo `COUNT(*)` es mayor que 1.

    Devuelve: `n_srs` (total de filas) y `colisiones` (lista de grupos).
    """
    n = int(conn.execute("SELECT COUNT(*) AS n FROM srs_estado").fetchone()["n"])
    grupos = conn.execute(
        """
        SELECT entidad, norma, articulo, chunk_id, nivel,
               COUNT(*) AS n,
               COUNT(DISTINCT modulo_id) AS modulos_distintos,
               array_agg(modulo_id ORDER BY modulo_id) AS modulo_ids,
               array_agg(id ORDER BY id) AS srs_ids
        FROM srs_estado
        GROUP BY entidad, norma, articulo, chunk_id, nivel
        HAVING COUNT(*) > 1
        ORDER BY n DESC
        """
    ).fetchall()
    return {
        "n_srs": n,
        "colisiones": [dict(g) for g in grupos],
    }


def consolidar_colisiones_srs(conn) -> int:
    """Deja una sola fila de repaso por tema y borra las copias.

    Cómo: para cada colisión ordena las filas por más repeticiones (`reps`),
    luego por `next_due` más lejano y, si empatan, por el `id` menor. Conserva
    la primera y borra el resto. No confirma la transacción.

    Variables:
        conn: conexión Postgres ya abierta.
        grupos: colisiones detectadas por `verificar_colisiones_srs`.
        borradas: cuántas filas se eliminaron.
        rows: filas de un mismo tema, ya ordenadas.
        keep: id de la fila que se conserva (el resto se borra).

    Devuelve: cuántas filas se borraron.
    """
    grupos = verificar_colisiones_srs(conn)["colisiones"]
    borradas = 0
    for g in grupos:
        rows = conn.execute(
            """
            SELECT id, reps, next_due, ease, intervalo_dias, lapses, modulo_id
            FROM srs_estado
            WHERE entidad = %s AND norma = %s AND articulo = %s
              AND chunk_id = %s AND nivel = %s
            ORDER BY reps DESC NULLS LAST,
                     next_due DESC NULLS LAST,
                     id ASC
            """,
            (g["entidad"], g["norma"], g["articulo"], g["chunk_id"], g["nivel"]),
        ).fetchall()
        if len(rows) < 2:
            continue
        keep = int(rows[0]["id"])
        for r in rows[1:]:
            conn.execute("DELETE FROM srs_estado WHERE id = %s", (int(r["id"]),))
            borradas += 1
        _ = keep
    return borradas


def _renombrar_unique_srs(conn) -> None:
    """Cambia la clave única del repaso para que el módulo no parta el tema.

    Cómo: lee las restricciones UNIQUE de `srs_estado`. Si alguna incluye
    `modulo_id` y `chunk_id`, la elimina: esa versión antigua trataba el mismo
    artículo como dos repasos distintos según el módulo. Después crea, si aún
    no existe, la clave `(entidad, norma, articulo, chunk_id, nivel)`.

    Variables:
        conn: conexión Postgres ya abierta.
        rows: restricciones UNIQUE actuales, con su nombre (`conname`) y su definición (`def`).
        defn: definición en mayúsculas, para buscar `MODULO_ID`.
        name: nombre de la restricción que se va a soltar.
        exists: fila si la clave nueva ya está creada.
    """
    rows = conn.execute(
        """
        SELECT c.conname, pg_get_constraintdef(c.oid) AS def
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'srs_estado' AND c.contype = 'u'
        """
    ).fetchall()
    for r in rows:
        defn = (r["def"] or "").upper()
        name = r["conname"]
        # Antigua incluye MODULO_ID en las columnas
        if "MODULO_ID" in defn and "CHUNK_ID" in defn:
            conn.execute(f'ALTER TABLE srs_estado DROP CONSTRAINT "{name}"')
    # Nueva UNIQUE (idempotente)
    exists = conn.execute(
        """
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'srs_estado' AND c.contype = 'u'
          AND pg_get_constraintdef(c.oid) ILIKE '%norma%'
          AND pg_get_constraintdef(c.oid) ILIKE '%chunk_id%'
          AND pg_get_constraintdef(c.oid) NOT ILIKE '%modulo_id%'
        LIMIT 1
        """
    ).fetchone()
    if exists is None:
        conn.execute(
            """
            ALTER TABLE srs_estado
            ADD CONSTRAINT srs_estado_unidad_sin_modulo_key
            UNIQUE (entidad, norma, articulo, chunk_id, nivel)
            """
        )


def migrar_fase8_esquema(conn) -> dict[str, Any]:
    """Prepara el esquema de la fase 8 dentro de la transacción de `init_db`.

    Cómo, en orden:
    1. Crea `chunk_modulos` si no existe, para que un artículo pueda pertenecer
       a más de un módulo (Ley 594 va a `esp_06` y a `com_13`).
    2. Copia el módulo que cada chunk ya tenía en `chunks.modulo_id`.
    3. Si hay colisiones de repaso, las consolida.
    4. Si después de consolidar todavía hay duplicados, aborta.
    5. Ajusta la clave única del SRS.

    Variables:
        conn: conexión abierta. El `commit` lo hace `init_db`, no esta función.
        backfill: resultado del INSERT de enlaces chunk–módulo.
        n_backfill: filas insertadas, o el total de `chunk_modulos` si el driver
            no informa `rowcount`.
        prev / post: foto de las colisiones antes y después de consolidar.
        borradas: filas de `srs_estado` eliminadas.

    Devuelve: conteos de filas SRS, colisiones y enlaces, para poder revisarlos.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunk_modulos (
            chunk_id BIGINT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            modulo_id BIGINT NOT NULL REFERENCES modulos(id),
            PRIMARY KEY (chunk_id, modulo_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_modulos_modulo ON chunk_modulos (modulo_id)"
    )
    backfill = conn.execute(
        """
        INSERT INTO chunk_modulos (chunk_id, modulo_id)
        SELECT c.id, c.modulo_id FROM chunks c
        ON CONFLICT DO NOTHING
        """
    )
    # psycopg rowcount
    n_backfill = getattr(backfill, "rowcount", None)
    if n_backfill is None or n_backfill < 0:
        n_backfill = int(
            conn.execute("SELECT COUNT(*) AS n FROM chunk_modulos").fetchone()["n"]
        )

    prev = verificar_colisiones_srs(conn)
    borradas = 0
    if prev["colisiones"]:
        borradas = consolidar_colisiones_srs(conn)
    post = verificar_colisiones_srs(conn)
    if post["colisiones"]:
        raise RuntimeError(
            f"Aún hay colisiones SRS tras consolidar: {post['colisiones']}"
        )
    _renombrar_unique_srs(conn)
    return {
        "n_srs_antes": prev["n_srs"],
        "colisiones_antes": len(prev["colisiones"]),
        "filas_srs_borradas": borradas,
        "n_srs_despues": post["n_srs"],
        "colisiones_despues": len(post["colisiones"]),
        "chunk_modulos_filas": n_backfill,
    }
