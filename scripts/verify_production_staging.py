#!/usr/bin/env python3
"""Run production/staging verification checks (P5.8 production hardening bundle)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent


def _load_script_module(name: str, script_path: Path):
    spec = importlib.util.spec_from_file_location(name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verify module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _run_pytest(relative_test_path: str) -> None:
    test_path = _ROOT / relative_test_path
    if not test_path.is_file():
        raise RuntimeError(f"missing test file: {test_path}")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_path), "-q"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pytest failed for {relative_test_path}:\n{proc.stdout}\n{proc.stderr}"
        )


_P7_UNIT_TESTS = (
    "platform/tests/test_credit_pricing.py",
    "platform/tests/test_platform_model_allowlist.py",
    "platform/tests/test_hardware_gates.py",
    "platform/tests/test_creative_appeal.py",
    "platform/tests/test_assignment_long_poll.py",
)


def verify_production_staging(
    base_url: str,
    *,
    quick: bool = True,
    expect_dispatch: bool | None = None,
) -> dict[str, Any]:
    """Run staging verification checks. Quick mode skips slow live task flows."""
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")

    scripts = _ROOT / "scripts"
    results: dict[str, Any] = {"platform_url": clean, "mode": "quick" if quick else "full"}

    platform_mod = _load_script_module(
        "verify_production_platform", scripts / "verify_production_platform.py"
    )
    results["platform"] = platform_mod.verify_production_platform(
        clean,
        expect_dispatch=expect_dispatch,
        register_smoke=True,
    )

    if results["platform"].get("assignment_mode") == "dispatch":
        dispatch_mod = _load_script_module(
            "verify_dispatch_staging", scripts / "verify_dispatch_staging.py"
        )
        results["dispatch"] = dispatch_mod.verify_dispatch_staging(clean)

    versioning_mod = _load_script_module(
        "verify_agent_versioning_staging", scripts / "verify_agent_versioning_staging.py"
    )
    results["versioning"] = versioning_mod.verify_agent_versioning_staging(clean)

    cred_mod = _load_script_module(
        "verify_credibility_staging", scripts / "verify_credibility_staging.py"
    )
    results["credibility"] = cred_mod.verify_credibility_staging(
        clean,
        run_sim_tests=not quick,
        register_smoke=True,
    )

    _run_pytest("platform/tests/test_auth.py")
    results["unit_registration_auth"] = "passed"

    reg_auth_mod = _load_script_module(
        "verify_registration_auth", scripts / "verify_registration_auth.py"
    )
    expect_registration_auth: bool | None = None
    if _env_flag("AGENTSWARM_EXPECT_REGISTRATION_AUTH", default=False):
        expect_registration_auth = True
    elif _env_flag("AGENTSWARM_EXPECT_OPEN_REGISTRATION", default=False):
        expect_registration_auth = False
    else:
        enforced_raw = results["platform"].get("auth_enforced")
        if enforced_raw == "true":
            expect_registration_auth = True
        elif enforced_raw == "false":
            expect_registration_auth = False
    results["registration_auth"] = reg_auth_mod.verify_registration_auth_staging(
        clean,
        expect_enforced=expect_registration_auth,
    )

    model_mod = _load_script_module(
        "verify_model_allowlist_staging", scripts / "verify_model_allowlist_staging.py"
    )
    expect_model_allowlist: bool | None = None
    if _env_flag("AGENTSWARM_EXPECT_MODEL_ALLOWLIST", default=False):
        expect_model_allowlist = True
    elif _env_flag("AGENTSWARM_EXPECT_OPEN_MODEL_ALLOWLIST", default=False):
        expect_model_allowlist = False
    else:
        enforced_raw = results["platform"].get("models_enforced")
        if enforced_raw == "True":
            expect_model_allowlist = True
        elif enforced_raw == "False":
            expect_model_allowlist = False
    results["model_allowlist"] = model_mod.verify_model_allowlist_staging(
        clean,
        expect_enforced=expect_model_allowlist,
    )

    hardware_mod = _load_script_module(
        "verify_hardware_gates_staging", scripts / "verify_hardware_gates_staging.py"
    )
    expect_hardware: bool | None = None
    if _env_flag("AGENTSWARM_EXPECT_HARDWARE_GATES", default=False):
        expect_hardware = True
    elif _env_flag("AGENTSWARM_EXPECT_OPEN_HARDWARE_GATES", default=False):
        expect_hardware = False
    else:
        enforced_raw = results["platform"].get("hardware_enforced")
        if enforced_raw == "True":
            expect_hardware = True
        elif enforced_raw == "False":
            expect_hardware = False
    results["hardware_gates"] = hardware_mod.verify_hardware_gates_staging(
        clean,
        expect_enforced=expect_hardware,
    )

    external_mod = _load_script_module(
        "verify_external_contributor", scripts / "verify_external_contributor.py"
    )
    results["external"] = external_mod.verify_external_contributor(
        clean,
        run_task_flow=not quick,
    )

    _run_pytest("platform/tests/test_agent_versioning.py")
    results["unit_agent_versioning"] = "passed"
    _run_pytest("platform/tests/test_version_probation.py")
    results["unit_version_probation"] = "passed"
    _run_pytest("platform/tests/test_tournaments_bounties.py")
    results["unit_tournaments_bounties"] = "passed"
    if results["platform"].get("assignment_mode") == "dispatch":
        _run_pytest("platform/tests/test_dispatch.py")
        results["unit_dispatch"] = "passed"

    if not quick:
        for relative in _P7_UNIT_TESTS:
            _run_pytest(relative)
        results["unit_p7"] = "passed"

        if results["platform"].get("assignment_mode") == "dispatch":
            appeal_mod = _load_script_module(
                "verify_creative_appeal_staging",
                scripts / "verify_creative_appeal_staging.py",
            )
            results["creative_appeal"] = appeal_mod.verify_creative_appeal_staging(clean)

            if not _env_flag("AGENTSWARM_VERIFY_SKIP_SUBJECTIVE_DEMO", default=False):
                if os.environ.get("AGENTSWARM_ASSIGNMENT_SECRET", "").strip():
                    subjective_mod = _load_script_module(
                        "verify_volunteer_subjective_staging",
                        scripts / "verify_volunteer_subjective_staging.py",
                    )
                    min_reviewers = int(
                        os.environ.get("AGENTSWARM_VERIFY_SUBJECTIVE_MIN_REVIEWERS", "1")
                    )
                    results["volunteer_subjective"] = (
                        subjective_mod.verify_volunteer_subjective_staging(
                            clean,
                            min_reviewers=min_reviewers,
                        )
                    )
                else:
                    results["volunteer_subjective"] = "skipped_no_assignment_secret"

        if not _env_flag("AGENTSWARM_VERIFY_SKIP_NEWS", default=False):
            news_proc = subprocess.run(
                [sys.executable, str(scripts / "verify_news_pipeline.py")],
                cwd=_ROOT,
                env={**os.environ, "AGENTSWARM_PLATFORM_URL": clean},
                capture_output=True,
                text=True,
                check=False,
            )
            if news_proc.returncode != 0:
                raise RuntimeError(
                    "news pipeline verify failed:\n"
                    f"{news_proc.stdout}\n{news_proc.stderr}"
                )
            results["news_pipeline"] = "passed"
        else:
            results["news_pipeline"] = "skipped"

        if not _env_flag("AGENTSWARM_VERIFY_SKIP_MCP", default=False):
            mcp_proc = subprocess.run(
                [sys.executable, str(scripts / "verify_mcp_adapter.py")],
                cwd=_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if mcp_proc.returncode != 0:
                raise RuntimeError(
                    "mcp adapter verify failed:\n"
                    f"{mcp_proc.stdout}\n{mcp_proc.stderr}"
                )
            results["mcp_adapter"] = "passed"
        else:
            results["mcp_adapter"] = "skipped"

        if _env_flag("AGENTSWARM_VERIFY_SWARM", default=False):
            swarm_mod = _load_script_module(
                "verify_production_swarm", scripts / "verify_production_swarm.py"
            )
            results["swarm"] = swarm_mod.verify_production_swarm(clean)

    return results


def main() -> int:
    url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"),
        )
    )
    quick = _env_flag("AGENTSWARM_VERIFY_QUICK", default=True)
    if _env_flag("AGENTSWARM_VERIFY_FULL", default=False):
        quick = False

    expect_dispatch: bool | None = None
    if _env_flag("AGENTSWARM_EXPECT_DISPATCH", default=False):
        expect_dispatch = True
    if os.environ.get("AGENTSWARM_EXPECT_PULL", "").lower() in ("1", "true", "yes"):
        expect_dispatch = False

    try:
        result = verify_production_staging(url, quick=quick, expect_dispatch=expect_dispatch)
    except (ValueError, RuntimeError) as exc:
        print(f"Production staging verify failed: {exc}", file=sys.stderr)
        return 1

    mode = result.get("mode", "quick")
    print(f"Production staging OK ({mode}): {url.strip().rstrip('/')} ({result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
