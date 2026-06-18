#!/usr/bin/env python3
"""Live engineering goal path smoke on staging."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))

DEMO_SCRIPT = _ROOT / "scripts" / "demo_engineering_goal.py"


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("demo_engineering_goal", DEMO_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load demo module from {DEMO_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def resolve_engineering_verify_timeouts() -> tuple[float, float]:
    goal_timeout_sec = float(
        os.environ.get("AGENTSWARM_VERIFY_ENGINEERING_GOAL_TIMEOUT_SEC", "300")
    )
    wait_timeout_sec = float(
        os.environ.get("AGENTSWARM_VERIFY_ENGINEERING_WAIT_SEC", "60")
    )
    return goal_timeout_sec, wait_timeout_sec


def verify_engineering_goal_staging(
    base_url: str,
    *,
    fixture: str = "primes",
    goal_timeout_sec: float | None = None,
    wait_timeout_sec: float | None = None,
) -> dict[str, str]:
    """Run coordinator → codewriter → tester → reviewer engineering demo on staging."""
    clean = _clean_url(base_url)
    resolved_goal_timeout, resolved_wait_timeout = resolve_engineering_verify_timeouts()
    if goal_timeout_sec is None:
        goal_timeout_sec = resolved_goal_timeout
    if wait_timeout_sec is None:
        wait_timeout_sec = resolved_wait_timeout
    if not os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip():
        raise RuntimeError("AGENTSWARM_BOOTSTRAP_TOKEN is required for engineering verify")
    if not os.environ.get("AGENTSWARM_ASSIGNMENT_SECRET", "").strip():
        raise RuntimeError("AGENTSWARM_ASSIGNMENT_SECRET is required for engineering verify")

    demo = _load_demo_module()
    from agentswarm_agents.engineering_lab import default_verification_spec

    result = demo.run_engineering_goal_demo(
        clean,
        wait_timeout_sec=wait_timeout_sec,
        goal_timeout_sec=goal_timeout_sec,
        verification_spec=default_verification_spec(fixture),
        isolate_dispatch=True,
    )
    if result.get("goal_status") != "verified":
        raise RuntimeError(f"expected goal verified, got {result.get('goal_status')!r}")

    output: dict[str, str] = {
        "platform_url": clean,
        "goal_id": str(result["goal_id"]),
        "goal_status": str(result["goal_status"]),
        "goal_kind": str(result.get("goal_kind", "engineering")),
        "fixture": fixture,
        "model_id": str(result.get("model_id", "")),
    }

    deploy_mod_path = _ROOT / "scripts" / "deploy_staging_helpers.py"
    if deploy_mod_path.is_file():
        deploy_spec = importlib.util.spec_from_file_location(
            "deploy_staging_helpers", deploy_mod_path
        )
        if deploy_spec and deploy_spec.loader:
            deploy_mod = importlib.util.module_from_spec(deploy_spec)
            deploy_spec.loader.exec_module(deploy_mod)
            reviewer_owner = next(
                (
                    role["owner"]
                    for role in result.get("roles", [])
                    if "reviewer" in role.get("capabilities", [])
                ),
                None,
            )
            creds = result.get("_agent_credentials") or {}
            signoff_agents: list[tuple[str, bytes]] | None = None
            if reviewer_owner and reviewer_owner in creds:
                signoff_agents = [creds[reviewer_owner]]
            deploy_result = deploy_mod.verify_deploy_from_verified_goal_staging(
                clean,
                output["goal_id"],
                signoff_agents=signoff_agents,
            )
            output.update(deploy_result)

    return output


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"
    )
    fixture = os.environ.get("AGENTSWARM_VERIFY_ENGINEERING_FIXTURE", "primes")
    goal_timeout, wait_timeout = resolve_engineering_verify_timeouts()
    try:
        result = verify_engineering_goal_staging(
            base_url,
            fixture=fixture,
            goal_timeout_sec=goal_timeout,
            wait_timeout_sec=wait_timeout,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"Engineering goal staging verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Engineering goal staging OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
