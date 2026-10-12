"""Pydantic del JSON del XML. Citas en caso/enunciado/justificaciones = inválido."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

MODULOS_13 = frozenset(
    {
        "esp_01",
        "esp_02",
        "esp_03",
        "esp_04",
        "esp_05",
        "esp_06",
        "esp_07",
        "esp_08",
        "com_09",
        "com_10",
        "com_11",
        "com_12",
        "com_13",
    }
)

# artículo 7 / art. 7 / art 7 / ley 1952 — no se “limpia”: el ítem se descarta.
_CITA_RE = re.compile(
    r"(?i)(?:\bart[íi]culo\s+\d|\bart\.?\s*\d|\bley\s+\d{3,4})"
)

MAX_INTENTOS_FORMATO = 3


class ItemInvalido(ValueError):
    """El JSON de Gemini no sirve como pregunta. No se guarda.

    Variables:
        razon: código corto, `json` o `citas`.
        detalle: texto largo del fallo, el mismo que ve `str(exc)` si no hay otro.
    """

    def __init__(self, razon: str, detalle: str = "") -> None:
        """Guarda la razón corta y usa el detalle como mensaje.

        Variables:
            razon: `json` si falló la forma, `citas` si el texto nombra artículo o ley.
            detalle: explicación. Si viene vacía, el mensaje es `razon`.
        """
        self.razon = razon
        super().__init__(detalle or razon)


class OpcionLLM(BaseModel):
    """Una opción tal como la redactó el modelo, antes de barajar la letra.

    Variables:
        letra: A, B, C o D.
        texto: enunciado de la opción.
        puntaje: 5 (óptima), 2 (parcial) o 0 (incorrecta).
        categoria_distractor: tipo de error de las opciones 2 y 0. La de 5 no lo lleva.
        justificacion: por qué esa opción vale ese puntaje. No puede citar el artículo.
    """
    model_config = ConfigDict(extra="ignore")

    letra: str
    texto: str
    puntaje: int
    categoria_distractor: str | None = None
    justificacion: str

    @field_validator("letra", mode="before")
    @classmethod
    def _letra(cls, value: Any) -> str:
        """Normaliza la letra a mayúscula y exige A, B, C o D.

        Variables:
            value: lo que vino en el JSON, antes de validar.
        """
        letra = str(value or "").strip().upper()
        if letra not in {"A", "B", "C", "D"}:
            raise ValueError("letra debe ser A, B, C o D")
        return letra

    @field_validator("texto", "justificacion", mode="before")
    @classmethod
    def _no_vacio(cls, value: Any) -> str:
        """Exige texto en la opción y en su justificación.

        Variables:
            value: campo `texto` o `justificacion` del JSON.
        """
        texto = str(value or "").strip()
        if not texto:
            raise ValueError("texto y justificacion no pueden estar vacíos")
        return texto

    @field_validator("puntaje", mode="before")
    @classmethod
    def _puntaje(cls, value: Any) -> int:
        """Acepta solo los puntajes 0, 2 y 5.

        Variables:
            value: número o texto numérico del JSON.
            n: ese valor ya convertido a entero.
        """
        try:
            n = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("puntaje debe ser 0, 2 o 5") from exc
        if n not in (0, 2, 5):
            raise ValueError("puntaje debe ser 0, 2 o 5")
        return n

    @field_validator("categoria_distractor", mode="before")
    @classmethod
    def _categoria(cls, value: Any) -> str | None:
        """Deja la categoría del distractor en texto, o None si venía vacía.

        Variables:
            value: campo opcional del JSON.
            texto: el valor ya convertido a texto y sin espacios.
        """
        if value is None:
            return None
        texto = str(value).strip()
        return texto or None


class ItemLLM(BaseModel):
    """La pregunta completa que devolvió el modelo, ya con forma válida.

    Variables:
        modulo_codigo: módulo pedido. `validar_respuesta` lo reescribe con el
            código real, para no fiarse del que invente el modelo.
        caso: situación práctica. No puede nombrar «artículo N» ni «ley NNNN».
        enunciado: la pregunta. Misma regla de citas.
        opciones: exactamente cuatro, con letras A–D y puntajes 5, 2, 0, 0.
        advertencia: texto si el modelo dice que el fragmento no alcanza.
            Si viene llena, el ítem no se guarda.
    """
    model_config = ConfigDict(extra="ignore")

    modulo_codigo: str = ""
    caso: str
    enunciado: str
    opciones: list[OpcionLLM]
    advertencia: str | None = None

    @field_validator("caso", "enunciado", mode="before")
    @classmethod
    def _texto(cls, value: Any) -> str:
        """Exige caso y enunciado con algún carácter.

        Variables:
            value: campo `caso` o `enunciado`.
        """
        texto = str(value or "").strip()
        if not texto:
            raise ValueError("caso y enunciado no pueden estar vacíos")
        return texto

    @field_validator("advertencia", mode="before")
    @classmethod
    def _advertencia(cls, value: Any) -> str | None:
        """Convierte una advertencia vacía en None.

        Variables:
            value: campo opcional. None, "" o solo espacios quedan en None.
        """
        if value is None:
            return None
        texto = str(value).strip()
        return texto or None

    @field_validator("modulo_codigo", mode="before")
    @classmethod
    def _modulo(cls, value: Any) -> str:
        """Pasa el código de módulo a texto sin espacios.

        Variables:
            value: lo que vino en el JSON. Puede faltar.
        """
        return str(value or "").strip()

    @model_validator(mode="after")
    def _opciones_legales(self) -> ItemLLM:
        """Comprueba que el conjunto de opciones sea un ítem 5/2/0/0.

        Cómo: exige 4 opciones, las letras A–D una vez cada una, y los puntajes
        exactamente 5, 2, 0 y 0. La opción de 5 no lleva categoría de distractor;
        las de 2 y 0 sí.

        Variables:
            self.opciones: las cuatro opciones ya validadas una a una.
            letras: letras presentes.
            puntajes: puntajes ordenados, para compararlos con `[0, 0, 2, 5]`.

        Devuelve: el mismo ítem, si la combinación es legal.
        """
        if len(self.opciones) != 4:
            raise ValueError("debe haber exactamente 4 opciones")
        letras = [op.letra for op in self.opciones]
        if sorted(letras) != ["A", "B", "C", "D"]:
            raise ValueError("las letras A–D deben aparecer una vez cada una")
        puntajes = sorted(op.puntaje for op in self.opciones)
        if puntajes != [0, 0, 2, 5]:
            raise ValueError("puntajes: exactamente un 5, un 2 y dos 0")
        for op in self.opciones:
            if op.puntaje == 5:
                if op.categoria_distractor is not None:
                    raise ValueError("la opción de 5 no lleva categoria_distractor")
            elif not op.categoria_distractor:
                raise ValueError("las opciones de 2 y 0 requieren categoria_distractor")
        return self


def extraer_json(raw: str) -> dict[str, Any]:
    """Saca el objeto JSON del texto de Gemini, aunque venga envuelto.

    Cómo: quita una cerca ```json si la hay. Intenta `json.loads` con todo el
    texto. Si falla, recorta desde la primera `{` hasta la última `}` y lo
    intenta de nuevo. El resultado tiene que ser un diccionario.

    Variables:
        raw: respuesta cruda del modelo.
        texto: esa respuesta ya recortada y sin cercas.
        data: objeto parseado.
        inicio / fin: posiciones de la primera `{` y la última `}`.

    Devuelve: el diccionario del ítem.
    """
    texto = (raw or "").strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.I)
        texto = re.sub(r"\s*```$", "", texto)
    try:
        data = json.loads(texto)
    except json.JSONDecodeError:
        inicio = texto.find("{")
        fin = texto.rfind("}")
        if inicio < 0 or fin <= inicio:
            raise
        data = json.loads(texto[inicio : fin + 1])
    if not isinstance(data, dict):
        raise json.JSONDecodeError("se esperaba un objeto JSON", texto, 0)
    return data


def campos_con_cita(item: ItemLLM) -> list[str]:
    """Busca citas legales en el caso, el enunciado y las justificaciones.

    Cómo: el patrón detecta «artículo 7», «art. 7» y «ley 1952». Esas citas
    no se borran: la pregunta se descarta, porque el estudiante no debe ver
    el número del artículo en el enunciado.

    Variables:
        item: ítem ya parseado.
        hallados: nombres de campo donde apareció una cita
            (`caso`, `enunciado`, `justificacion_A`, …).

    Devuelve: la lista de campos. Vacía si el texto está limpio.
    """
    hallados: list[str] = []
    if _CITA_RE.search(item.caso):
        hallados.append("caso")
    if _CITA_RE.search(item.enunciado):
        hallados.append("enunciado")
    for op in item.opciones:
        if _CITA_RE.search(op.justificacion):
            hallados.append(f"justificacion_{op.letra}")
    return hallados


def validar_respuesta(raw: str, modulo_pedido: str) -> ItemLLM:
    """Acepta o rechaza el JSON de una generación.

    Cómo: extrae el objeto, lo valida como `ItemLLM` y busca citas. Si hay
    citas, lanza `ItemInvalido` con razón `citas`. Si la forma falla, la razón
    es `json`. Al final fuerza `modulo_codigo` al módulo que se pidió.

    Variables:
        raw: texto devuelto por Gemini.
        modulo_pedido: código real de esta query, por ejemplo `esp_08`.
        data: diccionario extraído.
        item: modelo ya validado.
        citas: campos donde apareció una cita.

    Devuelve: el `ItemLLM` con el módulo corregido.
    """
    try:
        data = extraer_json(raw)
    except json.JSONDecodeError as exc:
        raise ItemInvalido("json", str(exc)) from exc

    try:
        item = ItemLLM.model_validate(data)
    except ValidationError as exc:
        raise ItemInvalido("json", str(exc)) from exc

    citas = campos_con_cita(item)
    if citas:
        raise ItemInvalido("citas", ",".join(citas))

    item.modulo_codigo = modulo_pedido
    return item
