"""Helpers de solo lectura para la pantalla de práctica (Fase 7). Sin Gemini."""

from __future__ import annotations

import json
from typing import Any

from backend.db.connection import get_connection, obtener_item
from backend.srs.service import SrsError
from backend.srs.sm2 import NIVEL_CASO, iso_utc, utc_now

_LETRAS = ("A", "B", "C", "D")

_VACIO = {
    "para_hoy": 0,
    "nuevos": 0,
    "programados": 0,
    "dudosos": 0,
    "en_banco": 0,
    "intentos_totales": 0,
    "aciertos_optimos": 0,
    "parciales": 0,
    "fallos": 0,
}


def _parse_opciones(raw: str | None, *, con_justificacion: bool) -> list[dict[str, Any]]:
    """Convierte el JSON de opciones en cuatro filas A, B, C y D.

    Cómo: exige una lista de exactamente 4 objetos. Cada uno necesita letra
    A–D sin repetir, texto, y puntaje 5, 2 o 0. Si `con_justificacion` es
    verdadero (la matriz de corrección), cada opción además necesita
    `justificacion`. El resultado se ordena por letra.

    Variables:
        raw: texto JSON de `opciones_json` o de `matriz_json`.
        con_justificacion: True cuando se lee la matriz que se muestra tras responder.
        data: lista ya parseada.
        letras: letras vistas, para detectar duplicados.
        op: una opción cruda del JSON.
        letra, texto, puntaje: campos ya validados.
        fila: opción limpia que entra en la lista de salida.
        just: justificación, solo si se pidió.

    Devuelve: cuatro diccionarios ordenados A, B, C, D.
    """
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise SrsError("opciones/matriz del ítem no es JSON válido") from exc
    if not isinstance(data, list) or len(data) != 4:
        raise SrsError("el ítem no tiene exactamente 4 opciones")
    letras: set[str] = set()
    out: list[dict[str, Any]] = []
    for op in data:
        if not isinstance(op, dict):
            raise SrsError("opción inválida en el ítem")
        letra = str(op.get("letra") or "").strip().upper()
        texto = str(op.get("texto") or "").strip()
        try:
            puntaje = int(op.get("puntaje"))
        except (TypeError, ValueError) as exc:
            raise SrsError("puntaje de opción inválido") from exc
        if letra not in _LETRAS or not texto or puntaje not in (0, 2, 5):
            raise SrsError("opción incompleta o con letra/puntaje inválido")
        if letra in letras:
            raise SrsError("letras de opción duplicadas")
        letras.add(letra)
        fila: dict[str, Any] = {
            "letra": letra,
            "texto": texto,
            "puntaje": puntaje,
            "categoria_distractor": op.get("categoria_distractor"),
        }
        if con_justificacion:
            just = str(op.get("justificacion") or "").strip()
            if not just:
                raise SrsError("falta justificación en la matriz del ítem")
            fila["justificacion"] = just
        out.append(fila)
    if letras != set(_LETRAS):
        raise SrsError("las opciones deben ser exactamente A, B, C y D")
    out.sort(key=lambda o: o["letra"])
    return out


def item_completo_para_practica(item_id: int, *, conn=None) -> dict[str, Any]:
    """Carga pregunta + opciones + matriz. Si `conn` se pasa, no abre otra."""
    row = obtener_item(item_id, conn=conn)
    if row is None:
        raise SrsError(f"No existe el ítem {item_id}")
    opciones = _parse_opciones(row.get("opciones_json"), con_justificacion=False)
    matriz = _parse_opciones(row.get("matriz_json"), con_justificacion=True)
    out = dict(row)
    out["opciones"] = opciones
    out["matriz"] = matriz
    return out


def resumen_practica_modulo(
    *,
    entidad: str = "pgn",
    modulo_codigo: str = "esp_08",
    conn=None,
) -> dict[str, int]:
    """Cuenta cola y notas de un módulo. Si `conn` se pasa, no abre otra."""
    ahora = iso_utc(utc_now())
    own = conn is None
    if own:
        conn = get_connection()
    try:
        mod = conn.execute(
            """
            SELECT id FROM modulos
            WHERE entidad = %s AND codigo = %s
            """,
            (entidad, modulo_codigo),
        ).fetchone()
        if mod is None:
            return dict(_VACIO)
        modulo_id = int(mod["id"])

        # asume 1 solo chunk_id; revisar si algún día se soportan ítems multi-fragmento
        fila = conn.execute(
            """
            WITH items_m AS (
                SELECT i.id, i.entidad, i.modulo_id, i.norma, i.articulo,
                       i.chunk_ids, i.dudoso
                FROM items i
                WHERE i.entidad = %s AND i.modulo_id = %s
            ),
            clasificado AS (
                SELECT
                    i.id,
                    i.dudoso,
                    EXISTS (
                        SELECT 1 FROM intentos t WHERE t.item_id = i.id
                    ) AS tiene_intento,
                    s.next_due
                FROM items_m i
                LEFT JOIN srs_estado s
                  ON s.entidad = i.entidad
                 AND s.norma = i.norma
                 AND s.articulo = i.articulo
                 AND s.chunk_id = NULLIF(i.chunk_ids::jsonb->>0, '')::bigint
                 AND s.nivel = %s
            )
            SELECT
                COUNT(*)::int AS en_banco,
                COUNT(*) FILTER (WHERE dudoso = 1)::int AS dudosos,
                COUNT(*) FILTER (
                    WHERE dudoso = 0 AND NOT tiene_intento
                )::int AS nuevos,
                COUNT(*) FILTER (
                    WHERE dudoso = 0
                      AND tiene_intento
                      AND next_due IS NOT NULL
                      AND next_due <= %s
                )::int AS para_hoy,
                COUNT(*) FILTER (
                    WHERE dudoso = 0
                      AND tiene_intento
                      AND next_due IS NOT NULL
                      AND next_due > %s
                )::int AS programados
            FROM clasificado
            """,
            (entidad, modulo_id, NIVEL_CASO, ahora, ahora),
        ).fetchone()

        intentos = conn.execute(
            """
            SELECT
                COUNT(*)::int AS intentos_totales,
                COUNT(*) FILTER (WHERE t.puntaje = 5)::int AS aciertos_optimos,
                COUNT(*) FILTER (WHERE t.puntaje = 2)::int AS parciales,
                COUNT(*) FILTER (WHERE t.puntaje = 0)::int AS fallos
            FROM intentos t
            JOIN items i ON i.id = t.item_id
            WHERE i.entidad = %s AND i.modulo_id = %s
            """,
            (entidad, modulo_id),
        ).fetchone()

        return {
            "para_hoy": int(fila["para_hoy"] or 0),
            "nuevos": int(fila["nuevos"] or 0),
            "programados": int(fila["programados"] or 0),
            "dudosos": int(fila["dudosos"] or 0),
            "en_banco": int(fila["en_banco"] or 0),
            "intentos_totales": int(intentos["intentos_totales"] or 0),
            "aciertos_optimos": int(intentos["aciertos_optimos"] or 0),
            "parciales": int(intentos["parciales"] or 0),
            "fallos": int(intentos["fallos"] or 0),
        }
    finally:
        if own:
            conn.close()


def ultimos_intentos_modulo(
    *,
    entidad: str = "pgn",
    modulo_codigo: str = "esp_08",
    limit: int = 8,
    conn=None,
) -> list[dict[str, Any]]:
    """Trae los intentos más recientes de un módulo. Si `conn` se pasa, no abre otra."""
    if limit < 1:
        return []
    own = conn is None
    if own:
        conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT t.id, t.item_id, t.puntaje, t.respondido_en
            FROM intentos t
            JOIN items i ON i.id = t.item_id
            JOIN modulos m ON m.id = i.modulo_id
            WHERE i.entidad = %s AND m.codigo = %s
            ORDER BY t.respondido_en DESC, t.id DESC
            LIMIT %s
            """,
            (entidad, modulo_codigo, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()
