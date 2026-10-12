"""Validación de que /siguiente no filtre secretos."""

from __future__ import annotations

from typing import Any

_CLAVES_PROHIBIDAS_SIGUIENTE = frozenset(
    {
        "puntaje",
        "justificacion",
        "matriz",
        "categoria_distractor",
        "norma",
        "articulo",
        "chunk_ids",
    }
)


def assert_sin_secretos(obj: Any, path: str = "$") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _CLAVES_PROHIBIDAS_SIGUIENTE:
                raise AssertionError(f"clave prohibida {k!r} en {path}")
            assert_sin_secretos(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            assert_sin_secretos(v, f"{path}[{i}]")
