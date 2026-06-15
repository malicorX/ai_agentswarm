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

    external_mod = _load_script_module(
        "verify_external_contributor", scripts / "verify_external_contributor.py"
    )
    results["external"] = external_mod.verify_external_contributor(
        clean,
        run_task_flow=not quick,
    )

    _run_pytest("platform/tests/test_agent_versioning.py")
    results["unit_agent_versioning"] = "passed"
    _run_pytest("platform/tests/test_tournaments_bounties.py")
    results["unit_tournaments_bounties"] = "passed"

    if not quick:
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
