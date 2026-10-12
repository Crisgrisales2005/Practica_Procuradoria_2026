"""SM-2 adaptado a puntajes 5 / 2 / 0 del ítem PGN.

Puntaje 5 → q=5 (ease sube +0.1). Puntajes 2 y 0 bajan ease y acortan intervalo
(0 más urgente que 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


EASE_MIN = 1.3
EASE_INICIAL = 2.5
NIVEL_CASO = "caso"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class EstadoSrs:
    ease: float = EASE_INICIAL
    intervalo_dias: int = 0
    reps: int = 0
    lapses: int = 0
    next_due: str | None = None


def aplicar_puntaje(estado: EstadoSrs, puntaje: int, ahora: datetime | None = None) -> EstadoSrs:
    """Devuelve un nuevo EstadoSrs tras aplicar 5, 2 o 0."""
    if puntaje not in (0, 2, 5):
        raise ValueError("puntaje debe ser 0, 2 o 5")

    ahora = ahora or utc_now()
    ease = float(estado.ease)
    intervalo = int(estado.intervalo_dias)
    reps = int(estado.reps)
    lapses = int(estado.lapses)

    if puntaje == 5:
        # q = 5 → ease += 0.1
        q = 5
        reps = reps + 1
        if reps == 1:
            intervalo = 1
        elif reps == 2:
            intervalo = 6
        else:
            intervalo = max(1, round(intervalo * ease))
        ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        ease = max(EASE_MIN, ease)
        next_due = iso_utc(ahora + timedelta(days=intervalo))
        return EstadoSrs(
            ease=ease,
            intervalo_dias=intervalo,
            reps=reps,
            lapses=lapses,
            next_due=next_due,
        )

    if puntaje == 2:
        lapses = lapses + 1
        reps = 0
        intervalo = 1
        ease = max(EASE_MIN, ease - 0.15)
        next_due = iso_utc(ahora + timedelta(days=1))
        return EstadoSrs(
            ease=ease,
            intervalo_dias=intervalo,
            reps=reps,
            lapses=lapses,
            next_due=next_due,
        )

    # puntaje == 0
    lapses = lapses + 1
    reps = 0
    intervalo = 0
    ease = max(EASE_MIN, ease - 0.20)
    next_due = iso_utc(ahora)
    return EstadoSrs(
        ease=ease,
        intervalo_dias=intervalo,
        reps=reps,
        lapses=lapses,
        next_due=next_due,
    )
