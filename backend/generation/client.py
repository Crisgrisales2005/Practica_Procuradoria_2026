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
    """Gemini respondió que se acabó la cuota del día. El lote debe detenerse."""


class CuotaMinutoAgotada(Exception):
    """Tres respuestas 429 por minuto seguidas. No se hacen más llamadas en esta corrida."""


class DisponibilidadAgotada(Exception):
    """Tres errores 503 o 5xx seguidos. La API no está disponible ahora."""


class ProveedorNoSoportado(Exception):
    """`GENERATION_PROVIDER` no es `gemini`. Esta fase no llama a otro motor."""


class GeneracionError(Exception):
    """Falló la red, el SDK o la respuesta, por una causa distinta de la cuota."""


class _ErrorTransitorio(Exception):
    """429 por minuto o error 5xx: hay que esperar y repetir la misma llamada.

    Variables:
        tipo: `minuto` o `disponibilidad`, para contar el reintento.
        retry_after: segundos que pidió el servidor en la cabecera Retry-After, o None.
    """

    def __init__(
        self, message: str, *, tipo: str, retry_after: float | None
    ) -> None:
        """Guarda el tipo de fallo transitorio y cuánto conviene esperar.

        Variables:
            message: texto de la excepción original de la API.
            tipo: `minuto` o `disponibilidad`.
            retry_after: segundos sugeridos por el servidor, si vinieron.
        """
        super().__init__(message)
        self.tipo = tipo  # "minuto" | "disponibilidad"
        self.retry_after = retry_after


def _retry_after_segundos(exc: BaseException) -> float | None:
    """Lee cuántos segundos pide esperar la cabecera Retry-After, si existe.

    Cómo: busca `response.headers` en la excepción del SDK, en minúsculas o
    en el nombre canónico. Si el valor no es un número, lo ignora.

    Variables:
        exc: excepción de la API.
        response: respuesta HTTP colgada de la excepción, si el SDK la guardó.
        raw_headers: diccionario de cabeceras.

    Devuelve: los segundos, o None si no hay cabecera usable.
    """
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
    """Recorre un JSON anidado y entrega cada diccionario que encuentra.

    Cómo: si el nodo es un diccionario, lo entrega y sigue por sus valores.
    Si es una lista, sigue por cada elemento. El resto de tipos se ignora.
    Sirve para buscar `quotaId` sin depender de la profundidad del error.

    Variables:
        nodo: un trozo de `details` (dict, list u otro).

    Devuelve: un generador de diccionarios.
    """
    if isinstance(nodo, dict):
        yield nodo
        for valor in nodo.values():
            yield from _recorrer_details(valor)
    elif isinstance(nodo, list):
        for item in nodo:
            yield from _recorrer_details(item)


def _details_indican_cuota_diaria(details: Any) -> bool:
    """Dice si el error 429 es la cuota del día y no el límite por minuto.

    Cómo: recorre los diccionarios de `details` y mira campos estructurados
    (`quotaId`, `quotaMetric`, `limit`, `reason`). Si el texto contiene
    `perday`, `per_day`, `/day` o `daily`, es la cuota diaria. Un
    `RATE_LIMIT_EXCEEDED` sin esa marca se trata como límite por minuto.

    Variables:
        details: árbol que el SDK adjunta al error, o None.
        nodo: cada diccionario encontrado.
        clave / valor: un campo candidato y su texto.
        bajo: ese texto en minúsculas.
        reason: campo `reason` del mismo nodo.

    Devuelve: True solo cuando hay una marca explícita de cuota diaria.
    """
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
    """Clasifica un fallo del SDK de Gemini en día, minuto o disponibilidad.

    Cómo: solo mira excepciones `APIError`. Un `ServerError` 500–504 es
    disponibilidad. Un `ClientError` 429 es cuota del día si `details` lo dice,
    y límite por minuto en caso contrario. Un `ClientError` 5xx también cuenta
    como disponibilidad. Cualquier otra excepción devuelve None y se trata
    como error genérico de generación.

    Variables:
        exc: lo que lanzó `generate_content`.
        code: código HTTP, o 0 si no se puede leer.
        details: metadatos estructurados del 429.

    Devuelve: `dia`, `minuto`, `disponibilidad`, o None.
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
    """Versión corta de `clasificar_error_api` que solo informa cuotas.

    Cómo: reutiliza la clasificación completa y se queda con `dia` o `minuto`.
    Disponibilidad y el resto se devuelven como None.

    Variables:
        exc: excepción de la API.
        tipo: resultado de `clasificar_error_api`.

    Devuelve: `dia`, `minuto`, o None.
    """
    tipo = clasificar_error_api(exc)
    if tipo in {"dia", "minuto"}:
        return tipo
    return None


def _texto_respuesta(response: Any) -> str:
    """Junta el texto que devolvió Gemini, venga en `text` o en las partes.

    Cómo: si `response.text` tiene contenido, lo usa. Si no, recorre
    `candidates → content.parts` y concatena cada `part.text`.

    Variables:
        response: objeto que devolvió `generate_content`.
        texto: atajo `response.text`.
        candidates: lista de candidatos.
        partes: trozos de texto ya extraídos.

    Devuelve: el JSON en texto, o cadena vacía.
    """
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
    """Hace una llamada a Gemini y devuelve el JSON en texto.

    Cómo: crea el cliente con `GOOGLE_API_KEY` y pide JSON (`response_mime_type`).
    La temperatura es 0.3 y el tope de salida es 8192 tokens. El modelo sale de
    `settings.gemini_model`. Un 429 diario se convierte en `CuotaDia`. Un 429
    por minuto o un 5xx se convierte en `_ErrorTransitorio` para que
    `generar_json` pueda reintentar. El resto sube como `GeneracionError`.

    Variables:
        system: prompt maestro, el XML de `prompts/evaluator_elite_pgn.xml`.
        user: mensaje con el módulo y el fragmento normativo.
        client: cliente del SDK `google-genai`.
        config: instrucciones, temperatura y formato JSON.
        response: respuesta cruda del modelo.
        tipo: clasificación del error, si la llamada falló.
        texto: JSON devuelto.

    Devuelve: el texto de la respuesta, ya unido.
    """
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
    """Pide un ítem en JSON y reintenta los fallos pasajeros.

    Cómo: exige proveedor `gemini` y clave configurada. Llama a `_llamar` hasta
    tres veces. Cada 429 por minuto o 5xx espera al menos 60 segundos (o lo que
    diga Retry-After, si es mayor) y no cuenta como ítem mal formado. Al tercer
    fallo del mismo tipo lanza `CuotaMinutoAgotada` o `DisponibilidadAgotada`.
    La cuota diaria no se reintenta: sube enseguida como `CuotaDia`.

    Variables:
        system: instrucciones fijas del evaluador.
        user: fragmento y módulo de esta pregunta.
        n_429: cuántos 429 por minuto ocurrieron en esta generación.
        n_disp: cuántos 5xx ocurrieron.
        intento: número de prueba, de 1 a 3.
        espera: segundos de pausa antes del siguiente intento.

    Devuelve: `(texto_json, n_429, n_disp)`.
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
