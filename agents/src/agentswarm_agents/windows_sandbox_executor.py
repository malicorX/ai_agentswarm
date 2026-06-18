"""Run engineering build/test inside an isolated Windows VM (D4)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import textwrap
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from agentswarm_agents.engineering_lab import fixture_dir

DEFAULT_VM_NAME = "agentswarm-sandbox-win"
DEFAULT_GUEST_WORKDIR = r"C:\agentswarm\workspace"
MOCK_ENV = "AGENTSWARM_WINDOWS_SANDBOX_MOCK"
SNAPSHOT_ENV = "AGENTSWARM_WINDOWS_SNAPSHOT_NAME"
NETWORK_ISOLATED_ENV = "AGENTSWARM_WINDOWS_NETWORK_ISOLATED"


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def windows_sandbox_mock_enabled() -> bool:
    raw = os.environ.get(MOCK_ENV, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def windows_vm_name() -> str:
    return os.environ.get("AGENTSWARM_WINDOWS_VM_NAME", DEFAULT_VM_NAME).strip() or DEFAULT_VM_NAME


def guest_workdir() -> str:
    return os.environ.get("AGENTSWARM_WINDOWS_GUEST_WORKDIR", DEFAULT_GUEST_WORKDIR).strip()


def sandbox_host_owner() -> str:
    return os.environ.get("AGENTSWARM_VOLUNTEER_OWNER", "").strip() or "windows-sandbox-host"


def windows_snapshot_name() -> str:
    return os.environ.get(SNAPSHOT_ENV, "").strip()


def windows_network_isolated() -> bool:
    if windows_sandbox_mock_enabled():
        return False
    raw = os.environ.get(NETWORK_ISOLATED_ENV, "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _run_powershell(command: str, *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _restore_vm_snapshot(vm_name: str, snapshot_name: str) -> None:
    proc = _run_powershell(
        f"Restore-VMSnapshot -VMName '{vm_name}' -Name '{snapshot_name}' -Confirm:$false",
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"failed to restore snapshot {snapshot_name!r} on {vm_name!r}: "
            f"{(proc.stderr or proc.stdout)[-500:]}"
        )


def _set_vm_network_adapters(vm_name: str, *, enabled: bool) -> None:
    verb = "Enable-VMNetworkAdapter" if enabled else "Disable-VMNetworkAdapter"
    proc = _run_powershell(
        f"Get-VMNetworkAdapter -VMName '{vm_name}' | ForEach-Object {{ {verb} -VMNetworkAdapter $_ }}",
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"failed to {'enable' if enabled else 'disable'} network on {vm_name!r}: "
            f"{(proc.stderr or proc.stdout)[-500:]}"
        )


@contextmanager
def _vm_hardening_session(vm_name: str) -> Iterator[dict[str, Any]]:
    """Revert checkpoint snapshot and isolate guest network before sandbox work."""
    meta: dict[str, Any] = {
        "snapshot_reverted": False,
        "network_isolated": False,
    }
    snapshot = windows_snapshot_name()
    network_iso = windows_network_isolated()
    if windows_sandbox_mock_enabled():
        meta["mock"] = True
        if snapshot:
            meta["snapshot_reverted"] = True
        if network_iso:
            meta["network_isolated"] = True
        yield meta
        return
    if snapshot:
        _restore_vm_snapshot(vm_name, snapshot)
        meta["snapshot_reverted"] = True
        meta["snapshot_name"] = snapshot
    if network_iso:
        _set_vm_network_adapters(vm_name, enabled=False)
        meta["network_isolated"] = True
    try:
        yield meta
    finally:
        if network_iso:
            _set_vm_network_adapters(vm_name, enabled=True)


def _guest_command_for_fixture(fixture: str, phase: str) -> str:
    if fixture == "winhello":
        if phase == "compile":
            return textwrap.dedent(
                """
                python -m compileall -q .
                python -m pip install -q pyinstaller
                pyinstaller --onefile --name hello --distpath . hello.py
                if (-not (Test-Path '.\\hello.exe')) { exit 1 }
                """
            ).strip()
        return ".\\hello.exe"
    if phase == "compile":
        return "python -m compileall -q ."
    return "python -m pytest tests -q"


def hyperv_available() -> bool:
    if windows_sandbox_mock_enabled():
        return True
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-Module -ListAvailable Hyper-V) -ne $null",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return proc.returncode == 0 and "True" in proc.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def _vm_state(vm_name: str) -> str | None:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-VM -Name '{vm_name}' -ErrorAction SilentlyContinue).State",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        return None
    state = (proc.stdout or "").strip()
    return state or None


def _ensure_vm_running(vm_name: str) -> None:
    state = _vm_state(vm_name)
    if state is None:
        raise RuntimeError(
            f"Hyper-V VM {vm_name!r} not found; create it or set AGENTSWARM_WINDOWS_VM_NAME"
        )
    if state == "Running":
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Start-VM -Name '{vm_name}'"],
        check=True,
        timeout=120,
    )


def _invoke_guest_script(vm_name: str, guest_script: str) -> subprocess.CompletedProcess[str]:
    escaped = guest_script.replace("'", "''")
    ps = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        Invoke-Command -VMName '{vm_name}' -ScriptBlock {{
            {escaped}
        }}
        """
    ).strip()
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def _sync_fixture_to_guest(vm_name: str, host_fixture: Path, guest_root: str) -> None:
    """Copy fixture tree into the guest via a short-lived guest session."""
    archive = host_fixture.with_suffix(".zip")
    if archive.exists():
        archive.unlink()
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Compress-Archive -Path '{host_fixture}' -DestinationPath '{archive}' -Force",
        ],
        check=True,
        timeout=120,
    )
    try:
        guest_zip = f"{guest_root}\\fixture.zip"
        copy_script = textwrap.dedent(
            f"""
            New-Item -ItemType Directory -Force -Path '{guest_root}' | Out-Null
            """
        ).strip()
        _invoke_guest_script(vm_name, copy_script)
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    f"Copy-VMFile -Name '{vm_name}' -SourcePath '{archive}' "
                    f"-DestinationPath '{guest_zip}' -CreateFullPath -FileSource Host"
                ),
            ],
            check=True,
            timeout=120,
        )
        unpack_script = textwrap.dedent(
            f"""
            Expand-Archive -Path '{guest_zip}' -DestinationPath '{guest_root}' -Force
            Remove-Item -Force '{guest_zip}'
            """
        ).strip()
        proc = _invoke_guest_script(vm_name, unpack_script)
        if proc.returncode != 0:
            raise RuntimeError(
                f"guest fixture unpack failed: {(proc.stderr or proc.stdout)[-500:]}"
            )
    finally:
        archive.unlink(missing_ok=True)


def _mock_result(*, phase: str, verification_spec: dict[str, Any]) -> dict[str, Any]:
    fixture = str(verification_spec.get("fixture", "primes"))
    owner = sandbox_host_owner()
    vm = windows_vm_name()
    stdout = f"mock {phase} ok fixture={fixture} vm={vm}\n"
    hardening: dict[str, Any] = {}
    if windows_snapshot_name():
        hardening["snapshot_reverted"] = True
    if windows_network_isolated() or os.environ.get(NETWORK_ISOLATED_ENV, "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    ):
        hardening["network_isolated"] = True
    artifact = {
        "passed": True,
        "stdout_digest": _digest_text(stdout),
        "stderr_digest": _digest_text(""),
        "windows_vm": vm,
        "fixture": fixture,
        "sandbox_host_owner": owner,
        "mock": True,
        **hardening,
    }
    if phase == "compile":
        artifact["command"] = _guest_command_for_fixture(fixture, "compile")
        if fixture == "winhello":
            artifact["exe_built"] = True
        return {
            "passed": True,
            "returncode": 0,
            "fixture": fixture,
            "sandbox": True,
            "windows_vm": True,
            "windows_vm_name": vm,
            "mock": True,
            "stdout": stdout,
            "stderr": "",
            "sandbox_host_owner": owner,
            **hardening,
            "build_artifact": artifact,
        }
    artifact["exit_code"] = 0
    return {
        "passed": True,
        "returncode": 0,
        "fixture": fixture,
        "sandbox": True,
        "windows_vm": True,
        "windows_vm_name": vm,
        "mock": True,
        "stdout": stdout,
        "stderr": "",
        "sandbox_host_owner": owner,
        **hardening,
        "run_artifact": artifact,
    }


def _run_guest_phase(
    verification_spec: dict[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    if windows_sandbox_mock_enabled():
        return _mock_result(phase=phase, verification_spec=verification_spec)

    if not hyperv_available():
        raise RuntimeError(
            "Hyper-V is not available; install Hyper-V, configure a sandbox VM, "
            f"or set {MOCK_ENV}=1 for local mock runs"
        )

    fixture = str(verification_spec.get("fixture", "primes"))
    host_fixture = fixture_dir(fixture)
    if not host_fixture.is_dir():
        raise FileNotFoundError(f"engineering fixture not found: {fixture}")

    vm_name = windows_vm_name()
    guest_root = guest_workdir()
    guest_command = _guest_command_for_fixture(fixture, phase)
    with _vm_hardening_session(vm_name) as hardening:
        _ensure_vm_running(vm_name)
        _sync_fixture_to_guest(vm_name, host_fixture.resolve(), guest_root)

        guest_script = textwrap.dedent(
            f"""
            Set-Location '{guest_root}'
            {guest_command}
            if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
            """
        ).strip()
        proc = _invoke_guest_script(vm_name, guest_script)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    owner = sandbox_host_owner()
    passed = proc.returncode == 0
    base = {
        "passed": passed,
        "returncode": proc.returncode,
        "fixture": fixture,
        "sandbox": True,
        "windows_vm": True,
        "windows_vm_name": vm_name,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "sandbox_host_owner": owner,
        **hardening,
    }
    artifact = {
        "passed": passed,
        "stdout_digest": _digest_text(stdout),
        "stderr_digest": _digest_text(stderr),
        "windows_vm": vm_name,
        "fixture": fixture,
        "sandbox_host_owner": owner,
        **hardening,
    }
    if phase == "compile":
        artifact["command"] = guest_command.strip()
        if fixture == "winhello" and passed:
            artifact["exe_built"] = True
        base["build_artifact"] = artifact
    else:
        artifact["exit_code"] = proc.returncode
        base["run_artifact"] = artifact
    return base


def run_compile_windows_vm(verification_spec: dict[str, Any]) -> dict[str, Any]:
    """Compile-check engineering-lab sources inside a Windows VM."""
    return _run_guest_phase(verification_spec, phase="compile")


def run_fixture_tests_windows_vm(verification_spec: dict[str, Any]) -> dict[str, Any]:
    """Execute pytest for an engineering-lab fixture inside a Windows VM."""
    return _run_guest_phase(verification_spec, phase="test")
