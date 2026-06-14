from __future__ import annotations

import os
import secrets
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from agentswarm_platform.auth import create_owner_token, session_secret
from agentswarm_platform.deps import get_store
from agentswarm_platform.store import Store

router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"


def _public_base_url() -> str:
    return os.environ.get("AGENTSWARM_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")


def _oauth_configured() -> bool:
    return bool(
        os.environ.get("GITHUB_OAUTH_CLIENT_ID")
        and os.environ.get("GITHUB_OAUTH_CLIENT_SECRET")
    )


@router.get("/github")
def github_login() -> RedirectResponse:
    if not _oauth_configured():
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")
    state = secrets.token_urlsafe(16)
    params = urlencode(
        {
            "client_id": os.environ["GITHUB_OAUTH_CLIENT_ID"],
            "redirect_uri": f"{_public_base_url()}/auth/github/callback",
            "scope": "read:user",
            "state": state,
        }
    )
    return RedirectResponse(f"{GITHUB_AUTHORIZE}?{params}")


@router.get("/github/callback")
def github_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    store: Annotated[Store, Depends(get_store)] = ...,
) -> dict[str, Any]:
    if not _oauth_configured():
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")
    if not code:
        raise HTTPException(status_code=400, detail="missing code")
    if not os.environ.get("AGENTSWARM_SESSION_SECRET"):
        raise HTTPException(
            status_code=500,
            detail="AGENTSWARM_SESSION_SECRET must be set for OAuth",
        )

    token_response = httpx.post(
        GITHUB_TOKEN,
        headers={"Accept": "application/json"},
        data={
            "client_id": os.environ["GITHUB_OAUTH_CLIENT_ID"],
            "client_secret": os.environ["GITHUB_OAUTH_CLIENT_SECRET"],
            "code": code,
            "redirect_uri": f"{_public_base_url()}/auth/github/callback",
        },
        timeout=30.0,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="GitHub token exchange failed")

    user_response = httpx.get(
        GITHUB_USER,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30.0,
    )
    user_response.raise_for_status()
    user = user_response.json()
    github_user_id = str(user["id"])
    github_login = str(user["login"])

    owner = store.upsert_owner(github_user_id=github_user_id, github_login=github_login)
    owner_token = create_owner_token(
        owner_id=owner["owner_id"],
        github_user_id=github_user_id,
        github_login=github_login,
    )
    return {
        "owner_id": owner["owner_id"],
        "github_login": github_login,
        "owner_token": owner_token,
        "state": state,
    }
