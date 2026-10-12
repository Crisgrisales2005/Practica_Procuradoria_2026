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
    def __init__(self, razon: str, detalle: str = "") -> None:
        self.razon = razon
        super().__init__(detalle or razon)


class OpcionLLM(BaseModel):
    model_config = ConfigDict(extra="ignore")

    letra: str
    texto: str
    puntaje: int
    categoria_distractor: str | None = None
    justificacion: str

    @field_validator("letra", mode="before")
    @classmethod
    def _letra(cls, value: Any) -> str:
        letra = str(value or "").strip().upper()
        if letra not in {"A", "B", "C", "D"}:
            raise ValueError("letra debe ser A, B, C o D")
        return letra

    @field_validator("texto", "justificacion", mode="before")
    @classmethod
    def _no_vacio(cls, value: Any) -> str:
        texto = str(value or "").strip()
        if not texto:
            raise ValueError("texto y justificacion no pueden estar vacíos")
        return texto

    @field_validator("puntaje", mode="before")
    @classmethod
    def _puntaje(cls, value: Any) -> int:
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
        if value is None:
            return None
        texto = str(value).strip()
        return texto or None


class ItemLLM(BaseModel):
    model_config = ConfigDict(extra="ignore")

    modulo_codigo: str = ""
    caso: str
    enunciado: str
    opciones: list[OpcionLLM]
    advertencia: str | None = None

    @field_validator("caso", "enunciado", mode="before")
    @classmethod
    def _texto(cls, value: Any) -> str:
        texto = str(value or "").strip()
        if not texto:
            raise ValueError("caso y enunciado no pueden estar vacíos")
        return texto

    @field_validator("advertencia", mode="before")
    @classmethod
    def _advertencia(cls, value: Any) -> str | None:
        if value is None:
            return None
        texto = str(value).strip()
        return texto or None

    @field_validator("modulo_codigo", mode="before")
    @classmethod
    def _modulo(cls, value: Any) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def _opciones_legales(self) -> ItemLLM:
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
