#!/usr/bin/env python3
"""Staging e2e: D5 deploy-from-goal (+ optional verified engineering → deploy sign-off)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))


def _load_script_module(name: str, script_path: Path):
    spec = importlib.util.spec_from_file_location(name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def verify_staging_deploy_e2e(base_url: str) -> dict[str, Any]:
    """Run deploy bridge checks; optionally engineering goal → deploy-request → sign-offs."""
    clean = _clean_url(base_url)
    scripts = _ROOT / "scripts"
    result: dict[str, Any] = {"platform_url": clean}

    goal_deploy_mod = _load_script_module(
        "verify_goal_deploy_staging", scripts / "verify_goal_deploy_staging.py"
    )
    goal_deploy = goal_deploy_mod.verify_goal_deploy_staging(clean)
    result["goal_deploy"] = goal_deploy
    if goal_deploy.get("deploy_from_goal") == "skipped_not_deployed":
        raise RuntimeError(
            "deploy-from-goal endpoint not deployed on staging (404); run deploy_platform_theebie"
        )
    if goal_deploy.get("deploy_from_goal") != "ok":
        raise RuntimeError(f"unexpected goal_deploy result: {goal_deploy}")

    if not _env_flag("AGENTSWARM_VERIFY_DEPLOY_E2E_ENGINEERING"):
        return result

    if not os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip():
        raise RuntimeError("AGENTSWARM_BOOTSTRAP_TOKEN required for engineering e2e")
    if not os.environ.get("AGENTSWARM_ASSIGNMENT_SECRET", "").strip():
        raise RuntimeError("AGENTSWARM_ASSIGNMENT_SECRET required for engineering e2e")

    os.environ.setdefault("AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL", "1")
    if _env_flag("AGENTSWARM_VERIFY_DEPLOY_SIGNOFF_CHAIN"):
        os.environ.setdefault("AGENTSWARM_VERIFY_DEPLOY_SIGNOFF_CHAIN", "1")

    engineering_mod = _load_script_module(
        "verify_engineering_goal_staging", scripts / "verify_engineering_goal_staging.py"
    )
    fixture = os.environ.get("AGENTSWARM_VERIFY_ENGINEERING_FIXTURE", "primes")
    engineering = engineering_mod.verify_engineering_goal_staging(clean, fixture=fixture)
    result["engineering_goal"] = engineering

    deploy_from_goal = engineering.get("deploy_from_goal")
    if deploy_from_goal and deploy_from_goal not in ("requested", "skipped_not_deployed"):
        result["deploy_from_verified_goal"] = deploy_from_goal
    elif deploy_from_goal == "requested":
        result["deploy_from_verified_goal"] = "ok"
        if engineering.get("deploy_signoffs") == "ok":
            result["deploy_signoffs"] = "ok"
        if engineering.get("deploy_execute") == "ok":
            result["deploy_execute"] = "ok"
    elif _env_flag("AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL"):
        raise RuntimeError(
            "engineering goal verified but deploy-from-goal did not run; "
            "set AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL=1"
        )

    return result


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"
    )
    try:
        result = verify_staging_deploy_e2e(base_url)
    except (ValueError, RuntimeError) as exc:
        print(f"Staging deploy e2e failed: {exc}", file=sys.stderr)
        return 1
    print(f"Staging deploy e2e OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
