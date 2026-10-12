"""Orquestación de práctica: siguiente, responder, progreso."""

from __future__ import annotations

from typing import Any

from backend.app.repositories import practice as repo
from backend.app.util.llano import proximo_repaso_llano, rol_de_puntaje
from backend.app.util.secrets import assert_sin_secretos
from backend.app.util.tokens import firmar_presentacion, verificar_presentacion
from backend.srs.service import SrsError
from backend.srs.sm2 import iso_utc, utc_now

# Solo para tests: fuerza excepción tras el advisory lock.
_FORCE_ERROR_AFTER_LOCK = False


def set_force_error_after_lock(value: bool) -> None:
    global _FORCE_ERROR_AFTER_LOCK
    _FORCE_ERROR_AFTER_LOCK = value


def listar_modulos_con_banco(conn, entidad: str = "pgn") -> list[dict]:
    return repo.listar_modulos_con_banco(conn, entidad)


def progreso_modulo(conn, *, entidad: str, modulo_codigo: str) -> dict:
    resumen = repo.resumen_modulo(
        conn, entidad=entidad, modulo_codigo=modulo_codigo
    )
    ultimos = repo.ultimos_intentos(
        conn, entidad=entidad, modulo_codigo=modulo_codigo, limit=8
    )
    # Más reciente a la derecha: la query viene DESC → invertir.
    puntajes = [int(u["puntaje"]) for u in reversed(ultimos)]
    return {
        "para_hoy": resumen["para_hoy"],
        "nuevos": resumen["nuevos"],
        "programados": resumen["programados"],
        "dudosos": resumen["dudosos"],
        "aciertos_optimos": resumen["aciertos_optimos"],
        "parciales": resumen["parciales"],
        "fallos": resumen["fallos"],
        "intentos_totales": resumen["intentos_totales"],
        "ultimos_intentos": puntajes,
    }


def obtener_siguiente(
    conn, *, entidad: str, modulo_codigo: str
) -> dict[str, Any]:
    banco = repo.en_banco(conn, entidad, modulo_codigo)
    if banco == 0:
        return {"estado": "sin_banco"}

    meta = repo.seleccionar_siguiente(
        conn, entidad=entidad, modulo_codigo=modulo_codigo
    )
    if meta is None:
        return {"estado": "sin_pendientes"}

    item_id = int(meta["id"])
    completo = repo.item_completo(conn, item_id)
    ultimo = repo.ultimo_intento_id(conn, item_id)
    token = firmar_presentacion(item_id=item_id, ultimo_intento_id=ultimo)
    opciones = [{"letra": o["letra"], "texto": o["texto"]} for o in completo["opciones"]]
    out = {
        "estado": "pregunta",
        "presentacion_token": token,
        "item_id": item_id,
        "caso": completo["caso"],
        "enunciado": completo["enunciado"],
        "opciones": opciones,
    }
    assert_sin_secretos(out)
    return out


def _matriz_feedback(
    completo: dict, letra_elegida: str
) -> list[dict[str, Any]]:
    out = []
    for op in completo["matriz"]:
        letra = op["letra"]
        puntaje = int(op["puntaje"])
        out.append(
            {
                "letra": letra,
                "texto": op["texto"],
                "rol": rol_de_puntaje(puntaje),
                "es_eleccion": letra == letra_elegida,
                "es_optima": puntaje == 5,
                "justificacion": op["justificacion"],
            }
        )
    return out


def _feedback_desde_item(
    conn,
    *,
    item_id: int,
    letra_elegida: str,
    puntaje: int,
) -> dict[str, Any]:
    completo = repo.item_completo(conn, item_id)
    srs_despues = None
    try:
        srs_despues = repo.srs_despues_de_item(conn, completo)
    except SrsError:
        srs_despues = None

    return {
        "estado": "feedback",
        "item_id": item_id,
        "letra_elegida": letra_elegida,
        "puntaje": puntaje,
        "resultado": rol_de_puntaje(puntaje),
        "matriz": _matriz_feedback(completo, letra_elegida),
        "cita": {"norma": completo["norma"], "articulo": completo["articulo"]},
        "proximo_repaso": proximo_repaso_llano(srs_despues),
    }


def responder_intento(
    conn,
    *,
    presentacion_token: str,
    letra: str,
) -> dict[str, Any]:
    """Orden: lock → presentación (replay) → ultimo_intento_id → registrar."""
    letra = (letra or "").strip().upper()
    if letra not in ("A", "B", "C", "D"):
        raise ValueError("letra_invalida")

    try:
        payload = verificar_presentacion(presentacion_token)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    item_id = payload["item_id"]
    nonce = payload["nonce"]
    ultimo_token = payload["ultimo_intento_id"]

    # Advisory lock por nonce (serializa dobles POST del mismo token).
    repo.advisory_lock_nonce(conn, nonce)

    if _FORCE_ERROR_AFTER_LOCK:
        raise RuntimeError("forced_error_after_lock")

    existente = repo.presentacion_consumida(conn, nonce)

    if existente is not None:
        if str(existente["letra_elegida"]).upper() != letra:
            raise LookupError("letra_distinta")
        # Replay idempotente: mismo feedback, 200.
        return _feedback_desde_item(
            conn,
            item_id=int(existente["item_id"]),
            letra_elegida=str(existente["letra_elegida"]).upper(),
            puntaje=int(existente["puntaje"]),
        )

    # Recién entonces: doble pestaña / otro token ya respondió el ítem.
    ultimo_actual = repo.ultimo_intento_id(conn, item_id)
    if ultimo_actual != ultimo_token:
        raise LookupError("ya_respondida")

    completo = repo.item_completo(conn, item_id)
    letra_a_puntaje = {o["letra"]: int(o["puntaje"]) for o in completo["opciones"]}
    if letra not in letra_a_puntaje:
        raise ValueError("letra_invalida")
    puntaje = letra_a_puntaje[letra]

    reg = repo.registrar(conn, item_id, puntaje)
    ahora = iso_utc(utc_now())
    repo.insertar_presentacion_consumida(
        conn,
        nonce=nonce,
        item_id=item_id,
        intento_id=reg["intento_id"],
        letra=letra,
        puntaje=puntaje,
        creado_en=ahora,
    )
    return _feedback_desde_item(
        conn, item_id=item_id, letra_elegida=letra, puntaje=puntaje
    )


def marcar_item_dudoso(conn, item_id: int, dudoso: bool = True) -> dict:
    return repo.marcar_item_dudoso(conn, item_id, dudoso=dudoso)
