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
    return DeployPolicy(
        required_signoffs=max(1, required),
        min_credibility=max(0.0, min_cred),
        signoff_capabilities=caps,
    )
