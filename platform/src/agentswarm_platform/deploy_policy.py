from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeployPolicy:
    required_signoffs: int = 2
    min_credibility: float = 50.0
    signoff_capabilities: tuple[str, ...] = ("reviewer", "deployer")


def resolve_deploy_policy(governance_config: dict[str, Any] | None) -> DeployPolicy:
    return resolve_deploy_policy_for_environment(governance_config, environment="")


def resolve_deploy_policy_for_environment(
    governance_config: dict[str, Any] | None,
    environment: str,
) -> DeployPolicy:
    deploy = (governance_config or {}).get("deploy") or {}
    if not isinstance(deploy, dict):
        deploy = {}
    default_required = int(os.environ.get("AGENTSWARM_DEPLOY_REQUIRED_SIGNOFFS", "2"))
    default_min = float(os.environ.get("AGENTSWARM_DEPLOY_MIN_CREDIBILITY", "50"))
    try:
        required = int(deploy.get("required_signoffs", default_required))
    except (TypeError, ValueError):
        required = default_required
    try:
        min_cred = float(deploy.get("min_credibility", default_min))
    except (TypeError, ValueError):
        min_cred = default_min
    raw_caps = deploy.get("signoff_capabilities", ["reviewer", "deployer"])
    if isinstance(raw_caps, str):
        caps = tuple(part.strip() for part in raw_caps.split(",") if part.strip())
    elif isinstance(raw_caps, list):
        caps = tuple(str(item).strip() for item in raw_caps if str(item).strip())
    else:
        caps = ("reviewer", "deployer")
    if not caps:
        caps = ("reviewer", "deployer")

    env_key = environment.strip().lower()
    envs = deploy.get("environments")
    if env_key and isinstance(envs, dict):
        overrides = envs.get(env_key)
        if isinstance(overrides, dict):
            if "required_signoffs" in overrides:
                try:
                    required = int(overrides["required_signoffs"])
                except (TypeError, ValueError):
                    pass
            if "min_credibility" in overrides:
                try:
                    min_cred = float(overrides["min_credibility"])
                except (TypeError, ValueError):
                    pass
            if "signoff_capabilities" in overrides:
                raw_env_caps = overrides["signoff_capabilities"]
                if isinstance(raw_env_caps, str):
                    caps = tuple(
                        part.strip() for part in raw_env_caps.split(",") if part.strip()
                    )
                elif isinstance(raw_env_caps, list):
                    caps = tuple(
                        str(item).strip()
                        for item in raw_env_caps
                        if str(item).strip()
                    )

    return DeployPolicy(
        required_signoffs=max(1, required),
        min_credibility=max(0.0, min_cred),
        signoff_capabilities=caps or ("reviewer", "deployer"),
    )


def deploy_approve_stake_tier(min_credibility: float) -> str:
    """Align deploy.approve claim tier with the request credibility floor."""
    from agentswarm_platform.credibility import TIER_HIGH_MIN, TIER_MEDIUM_MIN

    if min_credibility >= TIER_HIGH_MIN:
        return "high"
    if min_credibility >= TIER_MEDIUM_MIN:
        return "medium"
    return "low"
