"""Per-goal forge credentials for git engineering goals (D1)."""

from __future__ import annotations

import os
import sqlite3
import uuid
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agentswarm_platform.models import utc_now_iso


def forge_mint_enabled() -> bool:
    return os.environ.get("AGENTSWARM_FORGE_MINT_KEYS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def goal_branch_prefix(goal_id: str) -> str:
    if goal_id.startswith("goal-"):
        return f"agentswarm/{goal_id}"
    return f"agentswarm/goal-{goal_id}"


def ensure_forge_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS goal_forge_credentials (
            goal_id TEXT PRIMARY KEY,
            credential_id TEXT NOT NULL,
            repo_url TEXT NOT NULL,
            branch_prefix TEXT NOT NULL,
            private_key_pem TEXT,
            public_key_openssh TEXT,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        )
        """
    )


def _generate_deploy_keypair() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_openssh = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        .decode("utf-8")
    )
    return private_pem, public_openssh


def mint_goal_forge_credential(
    conn: sqlite3.Connection,
    *,
    goal_id: str,
    repo_url: str,
) -> dict[str, Any]:
    ensure_forge_schema(conn)
    existing = conn.execute(
        "SELECT * FROM goal_forge_credentials WHERE goal_id = ? AND revoked_at IS NULL",
        (goal_id,),
    ).fetchone()
    if existing is not None:
        return dict(existing)

    credential_id = f"forge-{uuid.uuid4().hex[:12]}"
    branch_prefix = goal_branch_prefix(goal_id)
    private_pem: str | None = None
    public_openssh: str | None = None
    if forge_mint_enabled():
        private_pem, public_openssh = _generate_deploy_keypair()

    created_at = utc_now_iso()
    conn.execute(
        """
        INSERT INTO goal_forge_credentials (
            goal_id, credential_id, repo_url, branch_prefix,
            private_key_pem, public_key_openssh, created_at, revoked_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            goal_id,
            credential_id,
            repo_url,
            branch_prefix,
            private_pem,
            public_openssh,
            created_at,
        ),
    )
    return {
        "goal_id": goal_id,
        "credential_id": credential_id,
        "repo_url": repo_url,
        "branch_prefix": branch_prefix,
        "private_key_pem": private_pem,
        "public_key_openssh": public_openssh,
        "created_at": created_at,
        "revoked_at": None,
    }


def get_goal_forge_credential(conn: sqlite3.Connection, goal_id: str) -> dict[str, Any] | None:
    ensure_forge_schema(conn)
    row = conn.execute(
        """
        SELECT * FROM goal_forge_credentials
        WHERE goal_id = ? AND revoked_at IS NULL
        """,
        (goal_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def revoke_goal_forge_credential(conn: sqlite3.Connection, goal_id: str) -> bool:
    ensure_forge_schema(conn)
    cur = conn.execute(
        """
        UPDATE goal_forge_credentials
        SET revoked_at = ?
        WHERE goal_id = ? AND revoked_at IS NULL
        """,
        (utc_now_iso(), goal_id),
    )
    return cur.rowcount > 0


def forge_credentials_for_assignment(
    credential: dict[str, Any],
    *,
    lease_expires_at: str,
) -> dict[str, Any]:
    branch_prefix = str(credential["branch_prefix"])
    repo_url = str(credential["repo_url"])
    envelope: dict[str, Any] = {
        "type": "forge_scope",
        "credential_id": str(credential["credential_id"]),
        "repo_url": repo_url,
        "branch_prefix": branch_prefix,
        "allowed_branches": [f"{branch_prefix}", f"{branch_prefix}/*"],
        "expires_at": lease_expires_at,
    }
    private_pem = credential.get("private_key_pem")
    if isinstance(private_pem, str) and private_pem.strip():
        envelope["type"] = "ssh_deploy_key"
        envelope["private_key_pem"] = private_pem.strip()
        public_key = credential.get("public_key_openssh")
        if isinstance(public_key, str) and public_key.strip():
            envelope["public_key_openssh"] = public_key.strip()
    return envelope


def goal_id_from_assignment_capsule(capsule: dict[str, Any]) -> str | None:
    for key in ("goal_id",):
        value = capsule.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = capsule.get("capsule")
    if isinstance(nested, dict):
        return goal_id_from_assignment_capsule(nested)
    return None
