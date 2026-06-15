#!/usr/bin/env python3
"""Live volunteer subjective path smoke on staging (P9.2)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))

DEMO_SCRIPT = _ROOT / "scripts" / "demo_volunteer_subjective.py"
PREP_SCRIPT = _ROOT / "scripts" / "prep_staging_subjective_verify.sh"


def _skip_prep() -> bool:
    raw = os.environ.get("AGENTSWARM_VERIFY_SKIP_PREP", "").strip().lower()
    return raw in ("1", "true", "yes")


def prep_staging_subjective_verify() -> None:
    """Restart staging platform so dispatch pool maintenance runs on a clean process."""
    if _skip_prep():
        return
    if sys.platform == "win32":
        prep = _ROOT / "scripts" / "prep_staging_subjective_verify.ps1"
        subprocess.run(
            ["powershell", "-File", str(prep)],
            check=True,
            cwd=_ROOT,
        )
        return
    if not PREP_SCRIPT.is_file():
        raise RuntimeError(f"missing prep script: {PREP_SCRIPT}")
    subprocess.run(["bash", str(PREP_SCRIPT)], check=True, cwd=_ROOT)


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("demo_volunteer_subjective", DEMO_SCRIPT)
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


def verify_volunteer_subjective_staging(
    base_url: str,
    *,
    min_reviewers: int = 1,
    goal_timeout_sec: float = 420.0,
    wait_timeout_sec: float = 60.0,
) -> dict[str, str]:
    """Run coordinator → creative → reviewers demo against staging."""
    clean = _clean_url(base_url)
    if not os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN", "").strip():
        raise RuntimeError(
            "AGENTSWARM_BOOTSTRAP_TOKEN is required for subjective demo verify"
        )
    if not os.environ.get("AGENTSWARM_ASSIGNMENT_SECRET", "").strip():
        raise RuntimeError(
            "AGENTSWARM_ASSIGNMENT_SECRET is required for subjective demo verify"
        )

    prep_staging_subjective_verify()

    demo = _load_demo_module()
    result = demo.run_volunteer_subjective_demo(
        clean,
        min_reviewers=min_reviewers,
        wait_timeout_sec=wait_timeout_sec,
        goal_timeout_sec=goal_timeout_sec,
    )
    if result.get("goal_status") != "verified":
        raise RuntimeError(
            f"expected goal verified, got {result.get('goal_status')!r}"
        )

    return {
        "platform_url": clean,
        "goal_id": str(result["goal_id"]),
        "goal_status": str(result["goal_status"]),
        "min_reviewers": str(result.get("min_reviewers", min_reviewers)),
        "model_id": str(result.get("model_id", "")),
    }


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"
    )
    min_reviewers = int(os.environ.get("AGENTSWARM_VERIFY_SUBJECTIVE_MIN_REVIEWERS", "1"))
    try:
        result = verify_volunteer_subjective_staging(
            base_url,
            min_reviewers=min_reviewers,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"Volunteer subjective staging verify failed: {exc}", file=sys.stderr)
        return 1
    print(f"Volunteer subjective staging OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
