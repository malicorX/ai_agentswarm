from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any


def _assignment_secret() -> bytes:
    secret = (
        os.environ.get("AGENTSWARM_ASSIGNMENT_SECRET")
        or os.environ.get("AGENTSWARM_SESSION_SECRET")
        or ""
    ).strip()
    if not secret:
        raise RuntimeError(
            "AGENTSWARM_ASSIGNMENT_SECRET or AGENTSWARM_SESSION_SECRET required for dispatch"
        )
    return secret.encode("utf-8")


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_assignment(payload: dict[str, Any]) -> str:
    digest = hmac.new(_assignment_secret(), _canonical(payload), hashlib.sha256).hexdigest()
    return digest


def verify_assignment(payload: dict[str, Any], signature: str) -> bool:
    expected = sign_assignment(payload)
    return hmac.compare_digest(expected, signature)
