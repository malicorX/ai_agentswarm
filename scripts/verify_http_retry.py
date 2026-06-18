"""Retry helpers for staging verify scripts (transient 5xx after platform restart)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import httpx

T = TypeVar("T")

_TRANSIENT_STATUS = frozenset({502, 503, 504})


def is_transient_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _TRANSIENT_STATUS
    return False


def retry_transient(
    fn: Callable[[], T],
    *,
    attempts: int = 6,
    delay_sec: float = 2.0,
    label: str = "request",
) -> T:
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except BaseException as exc:
            if not is_transient_http_error(exc) or attempt >= attempts:
                raise
            last = exc
            time.sleep(delay_sec)
    if last is not None:
        raise last
    raise RuntimeError(f"{label} failed without exception")
