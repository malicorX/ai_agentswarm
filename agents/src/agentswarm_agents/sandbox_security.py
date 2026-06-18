"""Docker sandbox security helpers (D3)."""

from __future__ import annotations

import os
from pathlib import Path

from agentswarm_agents.engineering_lab import engineering_lab_root

DEFAULT_TMPFS = "/tmp:rw,noexec,nosuid,size=128m"


def sandbox_hardening_enabled() -> bool:
    raw = os.environ.get("AGENTSWARM_SANDBOX_HARDEN", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def seccomp_profile_path() -> Path | None:
    override = os.environ.get("AGENTSWARM_SANDBOX_SECCOMP_PROFILE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    bundled = engineering_lab_root() / "seccomp-sandbox.json"
    return bundled if bundled.is_file() else None


def sandbox_container_name(run_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in run_id).strip("-")
    safe = safe[:48] or "run"
    return f"agentswarm-sandbox-{safe}"


def docker_security_args(*, read_only_root: bool = False) -> list[str]:
    """Extra `docker run` flags: cap drop, seccomp, optional read-only root, tmpfs."""
    if not sandbox_hardening_enabled():
        return []
    args = [
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
        f"--tmpfs={DEFAULT_TMPFS}",
    ]
    if read_only_root:
        args.append("--read-only")
    profile = seccomp_profile_path()
    if profile is not None:
        args.append(f"--security-opt=seccomp={profile.resolve()}")
    apparmor = os.environ.get("AGENTSWARM_SANDBOX_APPARMOR", "").strip()
    if apparmor:
        args.append(f"--security-opt=apparmor={apparmor}")
    return args


def cleanup_sandbox_container(run_id: str | None) -> None:
    """Remove a named sandbox container left over from a reclaimed lease (idempotent)."""
    if not run_id:
        return
    import subprocess

    name = sandbox_container_name(run_id)
    subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True,
        text=True,
        check=False,
    )
