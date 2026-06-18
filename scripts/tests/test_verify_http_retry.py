from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verify_http_retry import is_transient_http_error, retry_transient


def test_is_transient_http_error() -> None:
    response = httpx.Response(502, request=httpx.Request("GET", "https://example.test"))
    exc = httpx.HTTPStatusError("bad gateway", request=response.request, response=response)
    assert is_transient_http_error(exc) is True
    response404 = httpx.Response(404, request=httpx.Request("GET", "https://example.test"))
    exc404 = httpx.HTTPStatusError("missing", request=response404.request, response=response404)
    assert is_transient_http_error(exc404) is False


def test_retry_transient_recovers() -> None:
    calls = {"count": 0}

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            response = httpx.Response(503, request=httpx.Request("GET", "https://example.test"))
            raise httpx.HTTPStatusError("unavailable", request=response.request, response=response)
        return "ok"

    assert retry_transient(flaky, attempts=5, delay_sec=0) == "ok"
    assert calls["count"] == 3
