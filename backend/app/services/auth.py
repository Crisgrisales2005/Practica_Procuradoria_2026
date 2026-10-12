"""Auth de app: password + rate limit."""

from __future__ import annotations

import hmac

from backend.app.util import rate_limit
from backend.config import settings


def login_permitido(ip: str | None) -> bool:
    return rate_limit.login_allowed(ip)


def registrar_fallo(ip: str | None) -> None:
    rate_limit.register_login_failure(ip)


def password_correcta(given: str) -> bool:
    expected = settings.app_password or ""
    given = given or ""
    if not expected:
        return False
    return hmac.compare_digest(given, expected)
