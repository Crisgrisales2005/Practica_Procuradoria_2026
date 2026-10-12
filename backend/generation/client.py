"""Una llamada a Gemini 2.5 Flash.

429/minuto y 503/disponibilidad se reintentan con backoff y no cuentan
como fallo de validación de contenido. La cuota diaria corta el lote.
La clasificación usa tipo de excepción del SDK + código HTTP + campos
estructurados de `details`, no el texto libre del mensaje.
"""

from __future__ import annotations

import time
from typing import Any

from backend.config import settings

ESPACIADO_SEGUNDOS = 7.0
MAX_REINTENTOS_TRANSITORIOS = 3


class CuotaDia(Exception):
    """Cuota diaria (RPD) agotada: hay que cortar el lote."""


class CuotaMinutoAgotada(Exception):
    """Tres 429 por minuto seguidos: no seguir quemando llamadas."""


class DisponibilidadAgotada(Exception):
    """Tres 503/5xx seguidos: API no disponible."""


class ProveedorNoSoportado(Exception):
    """GENERATION_PROVIDER distinto de gemini."""


class GeneracionError(Exception):
    """Fallo de red o de SDK que no es cuota ni disponibilidad."""


class _ErrorTransitorio(Exception):
    """429/minuto o 5xx: esperar y reintentar la misma llamada."""

    def __init__(
        self, message: str, *, tipo: str, retry_after: float | None
    ) -> None:
        super().__init__(message)
        self.tipo = tipo  # "minuto" | "disponibilidad"
        self.retry_after = retry_after


def _retry_after_segundos(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    if response is not None:
        raw_headers = getattr(response, "headers", None) or {}
        for key in ("retry-after", "Retry-After"):
            if key in raw_headers:
                try:
                    return float(raw_headers[key])
                except (TypeError, ValueError):
                    pass
    return None


def _recorrer_details(nodo: Any):
    if isinstance(nodo, dict):
        yield nodo
        for valor in nodo.values():
            yield from _recorrer_details(valor)
    elif isinstance(nodo, list):
        for item in nodo:
            yield from _recorrer_details(item)


def _details_indican_cuota_diaria(details: Any) -> bool:
    """Mira metadatos estructurados (quotaId, quotaMetric, limit), no el message."""
    for nodo in _recorrer_details(details):
        for clave in ("quotaId", "quotaMetric", "quota_id", "quota_metric", "limit"):
            valor = nodo.get(clave)
            if not isinstance(valor, str):
                continue
            bajo = valor.lower()
            if (
                "perday" in bajo
                or "per_day" in bajo
                or "/day" in bajo
                or "_day_" in bajo
                or bajo.endswith("_day")
            ):
                return True
        reason = nodo.get("reason")
        if isinstance(reason, str):
            bajo = reason.lower()
            if "per_day" in bajo or "perday" in bajo or "daily" in bajo:
                return True
            # RATE_LIMIT_EXCEEDED = minuto; QUOTA_EXCEEDED sin day → no asumir día
    return False


def clasificar_error_api(exc: BaseException) -> str | None:
    """Devuelve 'dia' | 'minuto' | 'disponibilidad' | None.

    Solo por clase del SDK + code + details estructurados.
    """
    try:
        from google.genai.errors import APIError, ClientError, ServerError
    except ImportError:
        return None

    if not isinstance(exc, APIError):
        return None

    try:
        code = int(exc.code) if exc.code is not None else 0
    except (TypeError, ValueError):
        code = 0

    if isinstance(exc, ServerError) and code in (500, 502, 503, 504):
        return "disponibilidad"

    if isinstance(exc, ClientError) and code == 429:
        details = getattr(exc, "details", None)
        if _details_indican_cuota_diaria(details):
            return "dia"
        return "minuto"

    # Algunos backends envían 503 como ClientError
    if isinstance(exc, ClientError) and code in (500, 502, 503, 504):
        return "disponibilidad"

    return None


# Alias de compatibilidad para tests previos
def clasificar_cuota(exc: BaseException) -> str | None:
    tipo = clasificar_error_api(exc)
    if tipo in {"dia", "minuto"}:
        return tipo
    return None


def _texto_respuesta(response: Any) -> str:
    texto = getattr(response, "text", None)
    if texto:
        return str(texto)
    candidates = getattr(response, "candidates", None) or []
    partes: list[str] = []
    for cand in candidates:
        content = getattr(cand, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            t = getattr(part, "text", None)
            if t:
                partes.append(str(t))
    return "\n".join(partes).strip()


def _llamar(system: str, user: str) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeneracionError(
            "Falta el paquete google-genai. Instala requirements.txt."
        ) from exc

    client = genai.Client(api_key=settings.google_api_key)
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.3,
        max_output_tokens=8192,
        response_mime_type="application/json",
    )
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=user,
            config=config,
        )
    except Exception as exc:
        tipo = clasificar_error_api(exc)
        if tipo == "dia":
            raise CuotaDia(str(exc)) from exc
        if tipo in {"minuto", "disponibilidad"}:
            raise _ErrorTransitorio(
                str(exc),
                tipo=tipo,
                retry_after=_retry_after_segundos(exc),
            ) from exc
        raise GeneracionError(str(exc)) from exc

    texto = _texto_respuesta(response)
    if not texto.strip():
        raise GeneracionError("Gemini devolvió una respuesta vacía.")
    return texto


def generar_json(system: str, user: str) -> tuple[str, int, int]:
    """Una generación lógica. 429/minuto y 503 no cuentan como fallo de JSON.

    Devuelve (texto, n_429_minuto, n_disponibilidad).
    """
    if settings.provider_label != "gemini":
        raise ProveedorNoSoportado(
            f"GENERATION_PROVIDER={settings.generation_provider}. "
            "En esta fase solo está implementado gemini."
        )
    if not settings.has_google_api_key:
        raise GeneracionError("Falta GOOGLE_API_KEY.")

    n_429 = 0
    n_disp = 0
    for intento in range(1, MAX_REINTENTOS_TRANSITORIOS + 1):
        try:
            return _llamar(system, user), n_429, n_disp
        except _ErrorTransitorio as exc:
            if exc.tipo == "minuto":
                n_429 += 1
            else:
                n_disp += 1
            if intento >= MAX_REINTENTOS_TRANSITORIOS:
                if exc.tipo == "minuto":
                    raise CuotaMinutoAgotada(
                        "Tres 429 por minuto seguidos; corta el lote y reintenta más tarde."
                    ) from exc
                raise DisponibilidadAgotada(
                    "Tres errores de disponibilidad (503/5xx) seguidos; "
                    "corta el lote y reintenta más tarde."
                ) from exc
            espera = max(exc.retry_after or 60.0, 60.0)
            time.sleep(espera)
    raise DisponibilidadAgotada("No se pudo completar la llamada.")
