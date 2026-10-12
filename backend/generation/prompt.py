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
    """Lee el prompt maestro que se manda como instrucción de sistema.

    Cómo: abre `prompts/evaluator_elite_pgn.xml`. Ese XML le dice al modelo
    la forma del ítem 5/2/0/0 y las reglas de redacción.

    Devuelve: el XML completo en texto.
    Lanza: `FileNotFoundError` si el archivo no está.
    """
    if not _PROMPT_PATH.is_file():
        raise FileNotFoundError(f"No está el prompt maestro: {_PROMPT_PATH}")
    return _PROMPT_PATH.read_text(encoding="utf-8")


def armar_user_message(modulo_codigo: str, hits: list[Hit]) -> str:
    """Arma el mensaje de usuario con un solo artículo normativo.

    Cómo: escribe el código de módulo y, del primer hit, el `chunk_id`, la
    norma, el número de artículo y el texto completo. Cierra con la instrucción
    fija: generar un ítem usando solo ese fragmento, sin escribir el número de
    artículo, y llenar `advertencia` si el fragmento no alcanza.

    Variables:
        modulo_codigo: módulo de la query.
        hits: artículos recuperados. Solo se usa `hits[0]`.
        bloques: líneas que luego se unen con saltos de línea.
        hit: el fragmento que se inyecta.

    Devuelve: el mensaje de usuario, en texto plano.
    """
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
