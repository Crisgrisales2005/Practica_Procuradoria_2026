"""Pydantic request/response de la API web."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    password: str = Field(min_length=1)


class IntentoBody(BaseModel):
    presentacion_token: str
    letra: str


class DudosoBody(BaseModel):
    dudoso: bool = True
