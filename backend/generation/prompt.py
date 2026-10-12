"""System = XML maestro; user = módulo + fragmentos. Sin prosa libre."""

from __future__ import annotations

from pathlib import Path

from backend.rag.retrieve import Hit

_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "prompts"
    / "evaluator_elite_pgn.xml"
)

_INSTRUCCION = (
    "genera UN ítem usando SOLO este fragmento; no escribas norma ni número "
    "de artículo; si no alcanza, llena `advertencia` y no inventes."
)


def cargar_system_prompt() -> str:
    if not _PROMPT_PATH.is_file():
        raise FileNotFoundError(f"No está el prompt maestro: {_PROMPT_PATH}")
    return _PROMPT_PATH.read_text(encoding="utf-8")


def armar_user_message(modulo_codigo: str, hits: list[Hit]) -> str:
    bloques = [
        f"modulo_codigo: {modulo_codigo}",
        "",
        "Fragmento normativo (texto completo; no parafrasees):",
        "",
    ]
    # Un solo fragmento por generación (Regla de Oro = ese artículo).
    for hit in hits[:1]:
        bloques.extend(
            [
                "--- fragmento ---",
                f"chunk_id: {hit.chunk_id}",
                f"norma: {hit.norma}",
                f"articulo: {hit.articulo}",
                "texto:",
                hit.texto.strip(),
                "",
            ]
        )
    bloques.append(f"Instrucción: {_INSTRUCCION}")
    return "\n".join(bloques)
