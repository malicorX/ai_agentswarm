"""Install per-goal forge deploy keys into ssh authorized_keys (D1)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

MARKER_PREFIX = "# agentswarm-forge:"


def forge_auto_install_enabled() -> bool:
    return os.environ.get("AGENTSWARM_FORGE_AUTO_INSTALL_KEYS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def forge_auth_keys_path() -> Path:
    return Path(
        os.environ.get("AGENTSWARM_FORGE_AUTH_KEYS", "/root/.ssh/authorized_keys")
    )


def forge_git_shell_path() -> Path:
    override = os.environ.get("AGENTSWARM_FORGE_GIT_SHELL", "").strip()
    if override:
        return Path(override)
    root = os.environ.get("AGENTSWARM_INSTALL_ROOT", "/opt/agentswarm")
    return Path(root) / "scripts" / "remote" / "forge_git_shell.sh"


def bare_repo_path_from_url(repo_url: str) -> str:
    cleaned = repo_url.strip()
    if ":" in cleaned:
        return cleaned.split(":", 1)[1]
    return cleaned


def install_forge_deploy_public_key(credential: dict[str, Any]) -> bool:
    """Append a scoped forced-command entry for one forge credential. Idempotent."""
    credential_id = str(credential.get("credential_id") or "").strip()
    public_key = str(credential.get("public_key_openssh") or "").strip()
    repo_url = str(credential.get("repo_url") or "").strip()
    if not credential_id or not public_key or not repo_url:
        return False

    bare_path = bare_repo_path_from_url(repo_url)
    if not bare_path:
        return False

    auth_keys = forge_auth_keys_path()
    auth_keys.parent.mkdir(parents=True, exist_ok=True)
    if auth_keys.exists():
        existing = auth_keys.read_text(encoding="utf-8")
    else:
        existing = ""
        auth_keys.touch(mode=0o600)

    marker = f"{MARKER_PREFIX}{credential_id}"
    if marker in existing:
        return False

    shell = forge_git_shell_path()
    shell_ref = str(shell)
    entry = (
        f"{marker}\n"
        f'command="{shell_ref} {bare_path}",no-port-forwarding,no-X11-forwarding,'
        f"no-agent-forwarding,no-pty {public_key}\n"
    )
    with auth_keys.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    try:
        auth_keys.chmod(0o600)
    except OSError:
        pass
    return True
