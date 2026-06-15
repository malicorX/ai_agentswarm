from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

try:
    import jwt
except ImportError:  # pragma: no cover
    jwt = None  # type: ignore[assignment]


@dataclass(frozen=True)
class OwnerAuth:
    owner_id: str
    github_user_id: str
    github_login: str
    via_bootstrap: bool = False


def auth_enforced() -> bool:
    if os.environ.get("AGENTSWARM_AUTH_DISABLED", "").lower() in ("1", "true", "yes"):
        return False
    secret = os.environ.get("AGENTSWARM_SESSION_SECRET", "")
    bootstrap = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "")
    return bool(secret or bootstrap)


def session_secret() -> str:
    secret = os.environ.get("AGENTSWARM_SESSION_SECRET", "")
    if not secret and auth_enforced():
        raise RuntimeError("AGENTSWARM_SESSION_SECRET is required when auth is enforced")
    return secret or "dev-insecure-secret"


def bootstrap_token() -> str:
    return os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "")


def github_oauth_configured() -> bool:
    return bool(
        os.environ.get("GITHUB_OAUTH_CLIENT_ID")
        and os.environ.get("GITHUB_OAUTH_CLIENT_SECRET")
    )


def public_parameters() -> dict[str, bool]:
    """Read-only auth posture for /platform/config and staging verify."""
    enforced = auth_enforced()
    return {
        "enforced": enforced,
        "open_registration": not enforced,
        "github_oauth_configured": github_oauth_configured(),
        "bootstrap_token_configured": bool(bootstrap_token()),
    }


def dev_owner() -> OwnerAuth:
    return OwnerAuth(
        owner_id="owner_dev",
        github_user_id="0",
        github_login="dev",
        via_bootstrap=True,
    )


def create_owner_token(
    owner_id: str,
    github_user_id: str,
    github_login: str,
    *,
    ttl_seconds: int = 900,
) -> str:
    if jwt is None:
        raise RuntimeError("PyJWT is required for owner tokens; pip install PyJWT")
    now = int(time.time())
    payload = {
        "sub": owner_id,
        "gid": github_user_id,
        "login": github_login,
        "iat": now,
        "exp": now + ttl_seconds,
        "typ": "owner",
    }
    return jwt.encode(payload, session_secret(), algorithm="HS256")


def decode_owner_token(token: str) -> dict[str, Any]:
    if jwt is None:
        raise RuntimeError("PyJWT is required")
    return jwt.decode(token, session_secret(), algorithms=["HS256"])


def resolve_owner_auth(
    authorization: str | None,
    x_bootstrap_token: str | None,
) -> OwnerAuth:
    if not auth_enforced():
        return dev_owner()

    expected_bootstrap = bootstrap_token()
    if expected_bootstrap and x_bootstrap_token == expected_bootstrap:
        return OwnerAuth(
            owner_id="owner_bootstrap",
            github_user_id="bootstrap",
            github_login="bootstrap",
            via_bootstrap=True,
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="owner authentication required")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_owner_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid owner token") from exc

    if claims.get("typ") != "owner":
        raise HTTPException(status_code=401, detail="invalid token type")

    return OwnerAuth(
        owner_id=str(claims["sub"]),
        github_user_id=str(claims["gid"]),
        github_login=str(claims["login"]),
    )


def new_owner_id() -> str:
    return f"owner_{uuid.uuid4().hex[:12]}"
