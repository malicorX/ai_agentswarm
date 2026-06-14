from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from agentswarm_platform.crypto import generate_keypair, public_key_b64

from agentswarm_agents.client import PlatformClient, platform_url
from agentswarm_agents.owner_auth import owner_auth_headers


@dataclass
class StoredIdentity:
    agent_name: str
    agent_id: str
    public_key_b64: str
    private_key_b64: str
    owner: str
    capabilities: list[str]


def identity_dir() -> Path:
    override = os.environ.get("AGENTSWARM_IDENTITY_DIR")
    if override:
        return Path(override)
    return Path.home() / ".agentswarm" / "agents"


def identity_path(agent_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in agent_name)
    return identity_dir() / f"{safe}.json"


def save_identity(identity: StoredIdentity) -> None:
    path = identity_path(identity.agent_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(identity), indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def load_identity(agent_name: str) -> StoredIdentity | None:
    path = identity_path(agent_name)
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return StoredIdentity(
        agent_name=data["agent_name"],
        agent_id=data["agent_id"],
        public_key_b64=data["public_key_b64"],
        private_key_b64=data["private_key_b64"],
        owner=data["owner"],
        capabilities=list(data["capabilities"]),
    )


def _encode_keys(pub: bytes, priv: bytes) -> tuple[str, str]:
    return (
        public_key_b64(pub),
        base64.urlsafe_b64encode(priv).decode("ascii"),
    )


def _decode_keys(identity: StoredIdentity) -> tuple[bytes, bytes]:
    pub = base64.urlsafe_b64decode(identity.public_key_b64.encode("ascii"))
    priv = base64.urlsafe_b64decode(identity.private_key_b64.encode("ascii"))
    return pub, priv


def connect_agent(
    agent_name: str,
    owner: str,
    capabilities: list[str],
    base_url: str | None = None,
) -> PlatformClient:
    """Load or create persistent identity and connect to the platform."""
    url = (base_url or platform_url()).rstrip("/")
    stored = load_identity(agent_name)

    if stored:
        _, priv = _decode_keys(stored)
        pub_b64 = stored.public_key_b64
    else:
        pub, priv = generate_keypair()
        pub_b64, _ = _encode_keys(pub, priv)

    response = httpx.post(
        f"{url}/agents/register",
        json={
            "public_key": pub_b64,
            "owner": owner,
            "capabilities": capabilities,
        },
        headers=owner_auth_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    agent_id = response.json()["agent_id"]
    pub_b64, priv_b64 = _encode_keys(
        base64.urlsafe_b64decode(pub_b64.encode("ascii")), priv
    )
    save_identity(
        StoredIdentity(
            agent_name=agent_name,
            agent_id=agent_id,
            public_key_b64=pub_b64,
            private_key_b64=priv_b64,
            owner=owner,
            capabilities=capabilities,
        )
    )
    return PlatformClient(url, agent_id, priv)
