"""Diagnóstico del sistema: Supabase, banco, RAG. No es la pantalla de estudio diaria."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from backend.config import settings
from backend.db import DatabaseError

st.set_page_config(
    page_title="Diagnóstico — Sustanciador 4SU-11",
    page_icon="⚖️",
    layout="centered",
)

st.title("Diagnóstico del sistema")
st.caption("Procuraduría General de la Nación · Convocatoria 288-2026")

try:
    from backend.db import (
        contar_chunks,
        contar_chunks_vectorizados,
        contar_items,
        init_db,
        listar_documentos,
        listar_modulos,
    )

    init_db()
    modulos = listar_modulos("pgn")
    documentos = listar_documentos("pgn")
    n_chunks = contar_chunks("pgn")
    n_vectores = contar_chunks_vectorizados("pgn")
    n_items = contar_items("pgn")
except DatabaseError as exc:
    st.error(str(exc))
    st.stop()

st.info(
    "Datos relacionales en Supabase (PostgreSQL). "
    "Chroma y embeddings siguen locales. "
    "La práctica diaria está en la página principal (Home)."
)

st.subheader("Configuración cargada")
st.write(
    {
        "motor": settings.provider_label,
        "modelo_gemini": settings.gemini_model,
        "modelo_embeddings": settings.embedding_model,
        "rag_min_score": settings.rag_min_score,
        "api_key_gemini": "configurada" if settings.has_google_api_key else "pendiente",
        "database_url": "configurada" if settings.has_database_url else "pendiente",
        "chroma": str(settings.chroma_path),
        "documentos": str(settings.documentos_dir),
    }
)
st.caption("La API key y el DATABASE_URL nunca se muestran en pantalla.")

st.subheader("Módulos de conocimientos (convocatoria 288-2026)")
st.dataframe(
    [
        {
            "orden": m["orden"],
            "tipo": m["tipo"],
            "codigo": m["codigo"],
            "nombre": m["nombre"],
        }
        for m in modulos
    ],
    hide_index=True,
    use_container_width=True,
)

st.subheader("Banco de ítems")
st.write(f"Ítems en banco: **{n_items}**")
st.caption("Revisión humana en consola: `python scripts/revisar_items.py --last 5`.")

st.subheader("Normativa indexada")
st.write(f"Artículos en Postgres: **{n_chunks}** · con vector en Chroma: **{n_vectores}**")
if not documentos:
    st.warning(
        "No hay documentos indexados. Coloca el PDF y corre "
        "`python scripts/ingest_documento.py --manifest manifests/decreto_ley_262_2000.yaml`"
    )
else:
    st.dataframe(
        [
            {
                "archivo": d["nombre_archivo"],
                "fecha": d["fecha_carga"],
                "sha256": d["sha256"][:12] + "…",
            }
            for d in documentos
        ],
        hide_index=True,
        use_container_width=True,
    )

st.subheader("Búsqueda por módulo")
if n_vectores == 0:
    st.warning(
        "No hay vectores. Después de la ingesta del PDF corre:\n\n"
        "`python scripts/indexar_vectores.py`\n\n"
        "En Docker: `docker compose exec app python scripts/indexar_vectores.py`\n\n"
        "La primera vez descarga el modelo de embeddings (~1 GB). "
        "No recargues esta página para indexar: Streamlit no embebe al abrir."
    )
else:
    etiquetas = {m["codigo"]: f"{m['codigo']} — {m['nombre']}" for m in modulos}
    codigo = st.selectbox(
        "Módulo",
        options=[m["codigo"] for m in modulos],
        format_func=lambda c: etiquetas.get(c, c),
        index=next((i for i, m in enumerate(modulos) if m["codigo"] == "esp_08"), 0),
    )
    pregunta = st.text_input("Consulta", placeholder="Ej. funciones del Procurador General")
    if st.button("Buscar") and pregunta.strip():
        from backend.rag.retrieve import recuperar

        hits = recuperar(codigo, pregunta, k=5, entidad="pgn")
        if not hits:
            st.info("sin resultados")
        else:
            st.dataframe(
                [
                    {
                        "artículo": h.articulo,
                        "norma": h.norma,
                        "score": round(h.score, 3),
                        "extracto": " ".join(h.texto.split())[:240],
                    }
                    for h in hits
                ],
                hide_index=True,
                use_container_width=True,
            )

st.subheader("Ponderación del concurso (ficha informativa)")
st.markdown(
    """
| Tipo de prueba | Carácter | Peso | ¿Este sistema lo entrena? |
|---|---|---|---|
| Conocimientos | Eliminatoria (mínimo 65/100) | 60% | Sí, por los 13 módulos de arriba |
| Competencias comportamentales | Clasificatoria | 20% | No |
| Análisis de antecedentes | Clasificatoria | 20% | No |
"""
)
st.caption(
    "El progreso medible es por módulo de conocimientos (página de práctica). "
    "Comportamentales y antecedentes no se entrenan aquí. "
    "Lista de elegibles: puntaje final ≥ 70% (Art. 216, Decreto Ley 262 de 2000)."
)
