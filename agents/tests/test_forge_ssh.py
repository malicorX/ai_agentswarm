from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from agentswarm_agents.forge_ssh import (
    forge_git_env,
    normalize_deploy_key_pem,
    restrict_key_file_permissions,
    temp_deploy_key_file,
)


def _sample_deploy_key() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.OpenSSH,
        encryption_algorithm=NoEncryption(),
    ).decode("utf-8")
    public_openssh = (
        private_key.public_key()
        .public_bytes(
            encoding=Encoding.OpenSSH,
            format=PublicFormat.OpenSSH,
        )
        .decode("utf-8")
    )
    return private_pem, public_openssh


def test_normalize_deploy_key_pem_strips_crlf() -> None:
    private_pem, _ = _sample_deploy_key()
    crlf = private_pem.replace("\n", "\r\n")
    normalized = normalize_deploy_key_pem(crlf)
    assert "\r" not in normalized
    assert normalized.endswith("\n")
    assert "BEGIN OPENSSH PRIVATE KEY" in normalized


def test_forge_git_env_sets_ssh_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    private_pem, _ = _sample_deploy_key()
    monkeypatch.setenv("GIT_SSH_COMMAND", "")
    with forge_git_env(
        {
            "type": "ssh_deploy_key",
            "private_key_pem": private_pem,
        }
    ) as env:
        ssh_cmd = env.get("GIT_SSH_COMMAND", "")
        assert "IdentitiesOnly=yes" in ssh_cmd
        assert "BatchMode=yes" in ssh_cmd
        key_path = ssh_cmd.split('"')[1]
        assert Path(key_path).exists()
        restrict_key_file_permissions(Path(key_path))


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL helper")
def test_restrict_key_file_permissions_windows(tmp_path: Path) -> None:
    key_path = tmp_path / "deploy.key"
    private_pem, _ = _sample_deploy_key()
    key_path.write_text(private_pem, encoding="utf-8")
    restrict_key_file_permissions(key_path)
    proc = os.popen(f'icacls "{key_path}"')
    output = proc.read()
    proc.close()
    username = os.environ.get("USERNAME", "")
    assert username.lower() in output.lower()


@pytest.mark.skipif(shutil.which("ssh") is None, reason="openssh client not installed")
def test_openssh_loads_forge_deploy_key_without_libcrypto_error() -> None:
    """Regression: Windows OpenSSH must load temp forge keys (no libcrypto / ACL failure)."""
    private_pem, _ = _sample_deploy_key()
    crlf_pem = private_pem.replace("\n", "\r\n")
    with temp_deploy_key_file(crlf_pem) as key_path:
        proc = subprocess.run(
            [
                "ssh",
                "-i",
                str(key_path),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=5",
                "-T",
                "git@github.com",
            ],
            capture_output=True,
            text=True,
        )
    combined = f"{proc.stdout}\n{proc.stderr}".lower()
    assert "error in libcrypto" not in combined
    assert "permission denied" in combined
