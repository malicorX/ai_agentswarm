"""SSH deploy-key helpers for forge git operations (Windows + Unix)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_ssh_private_key,
)


def normalize_deploy_key_pem(key_pem: str) -> str:
    """Normalize forge deploy key PEM for OpenSSH (LF endings, valid OpenSSH format)."""
    cleaned = key_pem.strip().replace("\r\n", "\r").replace("\r", "\n")
    if not cleaned.endswith("\n"):
        cleaned += "\n"
    try:
        private_key = load_ssh_private_key(cleaned.encode("utf-8"), password=None)
        return private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.OpenSSH,
            encryption_algorithm=NoEncryption(),
        ).decode("utf-8")
    except ValueError:
        return cleaned


def restrict_key_file_permissions(key_path: Path) -> None:
    """OpenSSH refuses keys that are readable by other principals (notably on Windows)."""
    if os.name == "nt":
        username = os.environ.get("USERNAME", "").strip()
        if not username:
            return
        domain = os.environ.get("USERDOMAIN", "").strip()
        principal = f"{domain}\\{username}" if domain else username
        subprocess.run(
            ["icacls", str(key_path), "/inheritance:r"],
            check=False,
            capture_output=True,
        )
        subprocess.run(
            ["icacls", str(key_path), "/grant:r", f"{principal}:(R)"],
            check=False,
            capture_output=True,
        )
        return
    key_path.chmod(0o600)


def git_ssh_command_for_key(key_path: Path) -> str:
    return (
        f'ssh -i "{key_path}" -o IdentitiesOnly=yes '
        "-o StrictHostKeyChecking=accept-new -o BatchMode=yes"
    )


@contextmanager
def temp_deploy_key_file(key_pem: str) -> Iterator[Path]:
    normalized = normalize_deploy_key_pem(key_pem)
    fd, key_name = tempfile.mkstemp(prefix="agentswarm-forge-", suffix=".key")
    os.close(fd)
    key_path = Path(key_name)
    try:
        key_path.write_bytes(normalized.encode("utf-8"))
        restrict_key_file_permissions(key_path)
        yield key_path
    finally:
        key_path.unlink(missing_ok=True)


@contextmanager
def forge_git_env(credentials: dict[str, Any] | None) -> Iterator[dict[str, str]]:
    """Temporarily configure GIT_SSH_COMMAND for a scoped deploy key."""
    if not credentials:
        yield {}
        return
    key_pem = credentials.get("private_key_pem") or credentials.get("private_key")
    if credentials.get("type") != "ssh_deploy_key" or not isinstance(key_pem, str) or not key_pem.strip():
        yield {}
        return
    with temp_deploy_key_file(key_pem) as key_path:
        merged = os.environ.copy()
        merged["GIT_SSH_COMMAND"] = git_ssh_command_for_key(key_path)
        yield merged
