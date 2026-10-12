"""Frases de feedback en lenguaje llano."""

from __future__ import annotations


def proximo_repaso_llano(srs: dict | None) -> str | None:
    """Recalcula la frase de próximo repaso desde el SRS actual (replay documentado)."""
    if not srs:
        return None
    intervalo = int(srs.get("intervalo_dias") or 0)
    if intervalo <= 0:
        return "ahora mismo"
    if intervalo == 1:
        return "mañana"
    return f"en {intervalo} días"


def rol_de_puntaje(puntaje: int) -> str:
    if puntaje == 5:
        return "Óptima"
    if puntaje == 2:
        return "Parcial"
    return "Incorrecta"
