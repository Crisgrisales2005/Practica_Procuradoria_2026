"""Pantalla de práctica (Fase 7). Consume SRS; no llama a Gemini."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from backend.db import DatabaseError, ensure_pool, init_db, listar_modulos
from backend.srs import (
    SrsError,
    item_completo_para_practica,
    marcar_dudoso,
    registrar_intento,
    resumen_practica_modulo,
    siguiente_item,
    ultimos_intentos_modulo,
)

st.set_page_config(
    page_title="Práctica — Sustanciador 4SU-11",
    page_icon="⚖️",
    layout="centered",
)

DISCLAIMER = (
    "Herramienta de estudio. No garantiza un porcentaje de éxito en el examen oficial."
)


@st.cache_resource
def _warm_pool():
    return ensure_pool()


@st.cache_resource
def _init_db_once() -> bool:
    init_db()
    return True


@st.cache_data(ttl=120)
def _modulos_cached(entidad: str = "pgn") -> list[dict]:
    return listar_modulos(entidad)


def _init_state() -> None:
    defaults = {
        "practica_modulo": "esp_08",
        "practica_fase": "pregunta",
        "practica_item": None,
        "practica_letra": None,
        "practica_puntaje": None,
        "practica_srs": None,
        "practica_dudoso_ok": False,
        "practica_omitidos": set(),
        "practica_skip_msg": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if not isinstance(st.session_state.practica_omitidos, set):
        st.session_state.practica_omitidos = set(st.session_state.practica_omitidos or [])


def _limpiar_item() -> None:
    st.session_state.practica_item = None
    st.session_state.practica_letra = None
    st.session_state.practica_puntaje = None
    st.session_state.practica_srs = None
    st.session_state.practica_dudoso_ok = False
    st.session_state.practica_fase = "pregunta"


def _etiqueta_rol(puntaje: int) -> str:
    if puntaje == 5:
        return "Óptima (5)"
    if puntaje == 2:
        return "Parcial (2)"
    return "Incorrecta (0)"


def _frase_resultado(puntaje: int) -> str:
    if puntaje == 5:
        return "Respuesta óptima."
    if puntaje == 2:
        return "Respuesta parcial: conviene reforzar este punto."
    return "No era la mejor opción: revisa la justificación."


def _proximo_repaso_llano(srs: dict | None) -> str | None:
    if not srs:
        return None
    intervalo = int(srs.get("intervalo_dias") or 0)
    if intervalo <= 0:
        return "ahora mismo"
    if intervalo == 1:
        return "mañana"
    return f"en {intervalo} días"


def _pintar_panel_progreso(resumen: dict, modulo_codigo: str) -> None:
    st.subheader("Progreso de práctica")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Para hoy", int(resumen["para_hoy"]))
    c2.metric("Nuevos", int(resumen["nuevos"]))
    c3.metric("Programados", int(resumen["programados"]))
    c4.metric("Dudosos", int(resumen["dudosos"]))

    total = int(resumen["intentos_totales"])
    a1, a2, a3 = st.columns(3)
    a1.metric(
        "Aciertos óptimos",
        int(resumen["aciertos_optimos"]),
        help=f"Respuestas con puntaje 5 · de {total} intentos",
    )
    a2.metric(
        "Parciales",
        int(resumen.get("parciales", 0)),
        help=f"Respuestas con puntaje 2 · de {total} intentos",
    )
    a3.metric(
        "Fallos",
        int(resumen.get("fallos", 0)),
        help=f"Respuestas con puntaje 0 · de {total} intentos",
    )
    st.caption(f"{total} intentos en total (módulo)")

    st.markdown("**Últimos intentos**")
    try:
        recientes = ultimos_intentos_modulo(
            entidad="pgn",
            modulo_codigo=modulo_codigo,
            limit=8,
        )
    except DatabaseError as exc:
        st.error(str(exc))
        return

    if not recientes:
        st.caption("Aún no hay intentos en este módulo.")
    else:
        # más reciente a la derecha
        orden = list(reversed(recientes))
        cols = st.columns(len(orden))
        for col, intento in zip(cols, orden):
            p = int(intento["puntaje"])
            etiqueta = {5: "5", 2: "2", 0: "0"}.get(p, str(p))
            with col:
                if p == 5:
                    st.success(etiqueta)
                elif p == 2:
                    st.warning(etiqueta)
                else:
                    st.error(etiqueta)

    # disclaimer duplicado a propósito (panel + pie); no "limpiar" a una sola aparición
    st.info(DISCLAIMER)


def _cargar_siguiente(modulo: str) -> None:
    omitidos: set[int] = st.session_state.practica_omitidos
    while True:
        meta = siguiente_item(
            entidad="pgn",
            modulo_codigo=modulo,
            excluir_ids=omitidos,
        )
        if meta is None:
            st.session_state.practica_item = None
            return
        item_id = int(meta["id"])
        try:
            completo = item_completo_para_practica(item_id)
        except SrsError:
            omitidos.add(item_id)
            st.session_state.practica_omitidos = omitidos
            st.session_state.practica_skip_msg = (
                "Hubo un problema con esta pregunta. Pasamos a la siguiente."
            )
            continue
        completo["motivo"] = meta.get("motivo")
        st.session_state.practica_item = completo
        st.session_state.practica_fase = "pregunta"
        return


# --- UI ---
_init_state()

st.title("Preparación Sustanciador 4SU-11")
st.caption("Procuraduría General de la Nación · Convocatoria 288-2026")

try:
    with st.spinner("Conectando… puede tardar un minuto si Supabase estaba dormido"):
        _warm_pool()
        _init_db_once()
        modulos = _modulos_cached("pgn")
except DatabaseError as exc:
    st.error(str(exc))
    st.stop()

if not modulos:
    st.error("No hay módulos cargados en la base de datos.")
    st.stop()

etiquetas = {m["codigo"]: f"{m['codigo']} — {m['nombre']}" for m in modulos}
codigos = [m["codigo"] for m in modulos]
if "practica_select_modulo" not in st.session_state:
    st.session_state.practica_select_modulo = (
        "esp_08" if "esp_08" in codigos else codigos[0]
    )
if st.session_state.practica_select_modulo not in codigos:
    st.session_state.practica_select_modulo = codigos[0]

codigo = st.selectbox(
    "Módulo",
    options=codigos,
    format_func=lambda c: etiquetas.get(c, c),
    key="practica_select_modulo",
)

if codigo != st.session_state.practica_modulo:
    st.session_state.practica_modulo = codigo
    st.session_state.practica_omitidos = set()
    st.session_state.practica_skip_msg = None
    _limpiar_item()
    st.rerun()

try:
    resumen = resumen_practica_modulo(entidad="pgn", modulo_codigo=codigo)
except DatabaseError as exc:
    st.error(str(exc))
    st.stop()

_pintar_panel_progreso(resumen, codigo)

if st.session_state.practica_skip_msg:
    st.error(st.session_state.practica_skip_msg)
    st.session_state.practica_skip_msg = None

# Cargar ítem si hace falta
if (
    st.session_state.practica_fase == "pregunta"
    and st.session_state.practica_item is None
):
    try:
        with st.spinner("Cargando pregunta…"):
            _cargar_siguiente(codigo)
    except DatabaseError as exc:
        st.error(str(exc))
        st.stop()

item = st.session_state.practica_item

if item is None:
    if resumen["en_banco"] == 0:
        st.info(
            "Este módulo aún no tiene preguntas en el banco. "
            "Elige otro módulo (hoy el contenido está en Área disciplinar / esp_08)."
        )
    else:
        st.info(
            "Por ahora no hay más preguntas pendientes en este módulo. "
            "Las que ya respondiste volverán cuando toque repasarlas."
        )
else:
    if st.session_state.practica_fase == "pregunta":
        st.subheader("Caso")
        st.write(item["caso"])
        st.subheader("Pregunta")
        st.write(item["enunciado"])

        opciones = item["opciones"]
        labels = [f"{op['letra']}. {op['texto']}" for op in opciones]
        letra_a_puntaje = {op["letra"]: op["puntaje"] for op in opciones}

        eleccion = st.radio(
            "Elige una opción",
            options=labels,
            index=None,
            key=f"radio_{item['id']}",
        )
        letra_elegida = eleccion.split(".", 1)[0] if eleccion else None

        if st.button(
            "Responder",
            type="primary",
            disabled=(letra_elegida is None),
            key=f"btn_responder_{item['id']}",
        ):
            puntaje = letra_a_puntaje[letra_elegida]
            try:
                with st.spinner("Guardando respuesta…"):
                    resultado = registrar_intento(int(item["id"]), puntaje)
            except (DatabaseError, SrsError) as exc:
                st.error(str(exc))
            else:
                st.session_state.practica_letra = letra_elegida
                st.session_state.practica_puntaje = puntaje
                st.session_state.practica_srs = resultado.get("srs_despues")
                st.session_state.practica_fase = "feedback"
                st.rerun()

    elif st.session_state.practica_fase == "feedback":
        letra = st.session_state.practica_letra
        puntaje = st.session_state.practica_puntaje
        st.subheader("Resultado")
        frase = _frase_resultado(int(puntaje))
        if puntaje == 5:
            st.success(frase)
        elif puntaje == 2:
            st.warning(frase)
        else:
            st.error(frase)

        st.subheader("Calificación de cada opción")
        for op in item["matriz"]:
            rol = _etiqueta_rol(int(op["puntaje"]))
            marcas = []
            if op["letra"] == letra:
                marcas.append("Tu elección")
            if int(op["puntaje"]) == 5:
                marcas.append("Óptima")
            marca_txt = f" — {', '.join(marcas)}" if marcas else ""
            encabezado = f"**{op['letra']}.** {rol}{marca_txt}"
            cuerpo = f"{op['texto']}\n\n_{op['justificacion']}_"
            if int(op["puntaje"]) == 5:
                st.success(f"{encabezado}\n\n{cuerpo}")
            elif int(op["puntaje"]) == 2:
                st.warning(f"{encabezado}\n\n{cuerpo}")
            else:
                st.error(f"{encabezado}\n\n{cuerpo}")

        st.caption(f"Norma de apoyo: {item['norma']} · art. {item['articulo']}")

        llano = _proximo_repaso_llano(st.session_state.practica_srs)
        if llano:
            st.caption(f"Próximo repaso de este tema: {llano}.")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.session_state.practica_dudoso_ok:
                st.caption("Marcado como dudoso (no volverá a la cola).")
            elif st.button("Ítem dudoso", key=f"btn_dudoso_{item['id']}"):
                try:
                    with st.spinner("Marcando…"):
                        marcar_dudoso(int(item["id"]), True)
                except (DatabaseError, SrsError) as exc:
                    st.error(str(exc))
                else:
                    st.session_state.practica_dudoso_ok = True
                    st.rerun()
        with col_b:
            if st.button(
                "Siguiente",
                type="primary",
                key=f"btn_siguiente_{item['id']}",
            ):
                _limpiar_item()
                st.rerun()

st.divider()
# disclaimer duplicado a propósito (panel + pie); no "limpiar" a una sola aparición
st.caption(DISCLAIMER)
