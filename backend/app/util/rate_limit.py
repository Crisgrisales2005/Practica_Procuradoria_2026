"""Límites de login en memoria del proceso."""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_global_fails: list[float] = []
_ip_fails: dict[str, list[float]] = {}

WINDOW_S = 15 * 60
GLOBAL_MAX = 20
IP_MAX = 5


def _prune(ts_list: list[float], now: float) -> list[float]:
    return [t for t in ts_list if now - t < WINDOW_S]


def login_allowed(ip: str | None) -> bool:
    now = time.time()
    with _lock:
        global _global_fails
        _global_fails = _prune(_global_fails, now)
        if len(_global_fails) >= GLOBAL_MAX:
            return False
        if ip:
            fails = _prune(_ip_fails.get(ip, []), now)
            _ip_fails[ip] = fails
            if len(fails) >= IP_MAX:
                return False
    return True


def register_login_failure(ip: str | None) -> None:
    now = time.time()
    with _lock:
        global _global_fails
        _global_fails = _prune(_global_fails, now)
        _global_fails.append(now)
        if ip:
            fails = _prune(_ip_fails.get(ip, []), now)
            fails.append(now)
            _ip_fails[ip] = fails


def reset_for_tests() -> None:
    with _lock:
        global _global_fails
        _global_fails = []
        _ip_fails.clear()
