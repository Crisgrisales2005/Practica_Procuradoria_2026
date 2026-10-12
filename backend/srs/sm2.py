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
    """Hora actual en UTC, sin microsegundos.

    Devuelve: un `datetime` con zona UTC, para calcular el próximo repaso.
    """
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(dt: datetime) -> str:
    """Pasa una fecha a texto ISO en UTC, sin microsegundos.

    Cómo: si `dt` no trae zona horaria, se asume UTC. Luego se convierte a UTC
    y se formatea. Ese texto es el que se guarda en `next_due`.

    Variables:
        dt: fecha a guardar. Puede venir sin zona.

    Devuelve: por ejemplo `2026-10-13T18:31:00+00:00`.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class EstadoSrs:
    """Calendario de repaso de un tema, en memoria, antes o después de un intento.

    Variables:
        ease: factor de facilidad. Empieza en 2.5 y no baja de 1.3.
            Un ease alto alarga más rápido los intervalos cuando el puntaje es 5.
        intervalo_dias: días hasta el próximo repaso según la última cuenta.
        reps: aciertos óptimos seguidos. Vuelve a 0 con puntaje 2 o 0.
        lapses: veces que el puntaje fue 2 o 0.
        next_due: cuándo vuelve el tema, en texto ISO UTC. None si todavía no hay fila.
    """
    ease: float = EASE_INICIAL
    intervalo_dias: int = 0
    reps: int = 0
    lapses: int = 0
    next_due: str | None = None


def aplicar_puntaje(estado: EstadoSrs, puntaje: int, ahora: datetime | None = None) -> EstadoSrs:
    """Calcula el siguiente calendario de repaso a partir de la nota 5, 2 o 0.

    Cómo, con la hora `ahora` (o la hora UTC actual):
    - Puntaje 5 (óptima): suma una repetición. El primer acierto programa 1 día,
      el segundo 6 días y, a partir del tercero, `intervalo * ease` redondeado.
      El ease sube 0.1 (la fórmula SM-2 con calidad q=5 da exactamente +0.1).
    - Puntaje 2 (parcial): cuenta un fallo, pone repeticiones en 0, intervalo de
      1 día, resta 0.15 al ease y deja el repaso para mañana.
    - Puntaje 0 (incorrecta): cuenta un fallo, repeticiones en 0, intervalo 0,
      resta 0.20 al ease y deja el repaso para este mismo instante.
    El ease nunca queda por debajo de 1.3. El objeto de entrada no se modifica.

    Variables:
        estado: calendario anterior. Uno recién creado trae los valores iniciales.
        puntaje: 5, 2 o 0. Cualquier otro valor lanza `ValueError`.
        ahora: momento del intento. Si es None, se usa `utc_now()`.
        ease, intervalo, reps, lapses: copias numéricas del estado anterior.
        q: calidad SM-2; aquí siempre 5 en la rama de acierto.
        next_due: fecha ISO del próximo repaso.

    Devuelve: un `EstadoSrs` nuevo.
    """
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
