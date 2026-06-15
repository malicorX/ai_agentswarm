#!/usr/bin/env python3
"""Verify credibility spec parameters on a public staging platform (P5.4)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "agents" / "src"))
sys.path.insert(0, str(_ROOT / "platform" / "src"))

from agentswarm_agents.identity import connect_agent
from agentswarm_platform.credibility import (
    mint_for_acceptance,
    stake_amount,
    verifier_weight,
)

PILOT_PARAMS_PATH = _ROOT / "docs" / "infra" / "theebie" / "credibility-pilot-params.json"
SIM_TESTS = _ROOT / "platform" / "tests" / "test_credibility_sim.py"


def _clean_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("platform URL must start with https://")
    return clean


def load_expected_parameters(path: Path | None = None) -> dict[str, float | bool]:
    params_path = path or PILOT_PARAMS_PATH
    raw: dict[str, Any] = json.loads(params_path.read_text(encoding="utf-8"))
    return {key: value for key, value in raw.items() if key != "comment"}


def review_parameter_fairness(params: dict[str, float | bool]) -> dict[str, str]:
    """Human-review checklist from credibility-spec.md §7 — automated guards."""
    initial = float(params["initial_score"])
    base_mint = float(params["base_mint"])
    reviewer_mint = float(params["reviewer_mint"])
    stake = stake_amount(initial)
    max_submitter_mint = base_mint * 3 * verifier_weight(200.0)

    if stake >= initial:
        raise RuntimeError(
            f"stake {stake} should be below initial score {initial} at pilot settings"
        )
    if reviewer_mint >= max_submitter_mint:
        raise RuntimeError(
            "reviewer_mint must stay below worst-case submitter mint "
            f"({reviewer_mint} >= {max_submitter_mint})"
        )
    low_verifier_mint = mint_for_acceptance(task_tier=1, verifier_score=initial)
    if low_verifier_mint <= reviewer_mint:
        raise RuntimeError("submitter mint at low verifier should exceed reviewer_mint")

    return {
        "stake_at_initial": f"{stake}",
        "submitter_mint_low_verifier": f"{low_verifier_mint:.3f}",
        "reviewer_mint": f"{reviewer_mint}",
    }


def _compare_parameters(
    live: dict[str, float | bool],
    expected: dict[str, float | bool],
) -> None:
    for key, want in expected.items():
        if key not in live:
            raise RuntimeError(f"platform config missing credibility.{key}")
        got = live[key]
        if isinstance(want, bool):
            if bool(got) != want:
                raise RuntimeError(f"credibility.{key}: expected {want!r}, got {got!r}")
            continue
        if abs(float(got) - float(want)) > 1e-6:
            raise RuntimeError(f"credibility.{key}: expected {want}, got {got}")


def verify_credibility_staging(
    base_url: str,
    *,
    expected: dict[str, float | bool] | None = None,
    register_smoke: bool = True,
    run_sim_tests: bool = True,
) -> dict[str, str]:
    clean = _clean_url(base_url)
    want = expected or load_expected_parameters()
    result: dict[str, str] = {"platform_url": clean}

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        health = client.get(f"{clean}/health")
        health.raise_for_status()
        if health.json() != {"status": "ok"}:
            raise RuntimeError(f"unexpected /health body: {health.json()!r}")
        result["health"] = "ok"

        config = client.get(f"{clean}/platform/config")
        config.raise_for_status()
        body = config.json()
        live_cred = body.get("credibility")
        if not isinstance(live_cred, dict):
            raise RuntimeError("platform config missing credibility block")
        _compare_parameters(live_cred, want)
        result["parameters"] = "match_pilot"
        if not live_cred.get("enabled"):
            raise RuntimeError("AGENTSWARM_CREDIBILITY_ENABLED is off on platform")

        fairness = review_parameter_fairness(live_cred)
        result.update(fairness)

        if register_smoke:
            agent_name = f"cred-verify-{uuid.uuid4().hex[:8]}"
            override_dir = os.environ.get("AGENTSWARM_CRED_VERIFY_IDENTITY_DIR", "")
            temp_identity: tempfile.TemporaryDirectory[str] | None = None
            if override_dir:
                identity_dir = Path(override_dir)
                identity_dir.mkdir(parents=True, exist_ok=True)
            else:
                temp_identity = tempfile.TemporaryDirectory(prefix="agentswarm-cred-verify-")
                identity_dir = Path(temp_identity.name)
            os.environ["AGENTSWARM_IDENTITY_DIR"] = str(identity_dir)

            connected = connect_agent(
                agent_name=agent_name,
                owner="credibility-verify",
                capabilities=["reviewer"],
                base_url=clean,
            )
            result["agent_id"] = connected.agent_id

            cred_resp = client.get(f"{clean}/agents/{connected.agent_id}/credibility")
            cred_resp.raise_for_status()
            cred_body = cred_resp.json()
            balances = cred_body.get("capabilities", cred_body)
            if not isinstance(balances, list):
                raise RuntimeError("unexpected credibility response shape")
            reviewer_rows = [
                row for row in balances if row.get("capability") == "reviewer"
            ]
            if not reviewer_rows:
                raise RuntimeError("new agent missing reviewer credibility balance")
            score = float(reviewer_rows[0]["score"])
            initial = float(live_cred["initial_score"])
            if abs(score - initial) > 1e-6:
                raise RuntimeError(
                    f"seed score {score} != initial_score {initial} for new agent"
                )
            result["seed_score"] = f"{score}"
            if temp_identity is not None:
                temp_identity.cleanup()

    if run_sim_tests and SIM_TESTS.is_file():
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(SIM_TESTS), "-q"],
            cwd=_ROOT / "platform",
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "credibility simulation tests failed:\n"
                f"{proc.stdout}\n{proc.stderr}"
            )
        result["simulation_tests"] = "passed"

    return result


def main() -> int:
    url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get(
            "AGENTSWARM_PLATFORM_URL",
            os.environ.get("AGENTSWARM_STAGING_API_URL", "https://theebie.de/agentswarm/api"),
        )
    )
    skip_sim = os.environ.get("AGENTSWARM_CRED_SKIP_SIM", "").lower() in (
        "1",
        "true",
        "yes",
    )

    try:
        result = verify_credibility_staging(url, run_sim_tests=not skip_sim)
    except (ValueError, RuntimeError, httpx.HTTPError, json.JSONDecodeError) as exc:
        print(f"Credibility staging verify failed: {exc}", file=sys.stderr)
        return 1

    print(f"Credibility staging OK: {url.strip().rstrip('/')} ({result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
