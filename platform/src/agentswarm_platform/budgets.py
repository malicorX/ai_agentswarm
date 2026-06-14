from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from agentswarm_platform.capabilities import (
    capabilities_requiring_explicit_egress,
    load_capability_registry,
)

_HOSTNAME_RE = re.compile(
    r"^(?:\*\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?|[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


@dataclass(frozen=True)
class ResourceBudget:
    max_concurrent_claims: int
    max_claims_per_hour: int

    def as_dict(self) -> dict[str, int]:
        return {
            "max_concurrent_claims": self.max_concurrent_claims,
            "max_claims_per_hour": self.max_claims_per_hour,
        }


def platform_default_budget() -> ResourceBudget:
    return ResourceBudget(
        max_concurrent_claims=int(
            os.environ.get("AGENTSWARM_DEFAULT_MAX_CONCURRENT_CLAIMS", "2")
        ),
        max_claims_per_hour=int(
            os.environ.get("AGENTSWARM_DEFAULT_MAX_CLAIMS_PER_HOUR", "30")
        ),
    )


def _capability_entry(capability_id: str) -> dict[str, Any] | None:
    for item in load_capability_registry().get("capabilities", []):
        if item.get("id") == capability_id:
            return item
    return None


def default_budget_for_capabilities(capabilities: list[str]) -> ResourceBudget:
    platform = platform_default_budget()
    concurrent = platform.max_concurrent_claims
    hourly = platform.max_claims_per_hour
    for cap in capabilities:
        entry = _capability_entry(cap)
        if entry is None:
            continue
        cap_budget = entry.get("default_budget") or {}
        if "max_concurrent_claims" in cap_budget:
            concurrent = min(concurrent, int(cap_budget["max_concurrent_claims"]))
        if "max_claims_per_hour" in cap_budget:
            hourly = min(hourly, int(cap_budget["max_claims_per_hour"]))
    return ResourceBudget(max_concurrent_claims=concurrent, max_claims_per_hour=hourly)


def resolve_resource_budget(
    capabilities: list[str],
    override: dict[str, Any] | None,
) -> ResourceBudget:
    base = default_budget_for_capabilities(capabilities)
    if override is None:
        return base
    concurrent = int(override.get("max_concurrent_claims", base.max_concurrent_claims))
    hourly = int(override.get("max_claims_per_hour", base.max_claims_per_hour))
    if concurrent < 1 or hourly < 1:
        raise ValueError("resource budget limits must be positive integers")
    return ResourceBudget(max_concurrent_claims=concurrent, max_claims_per_hour=hourly)


def default_egress_for_capabilities(capabilities: list[str]) -> list[str]:
    hosts: set[str] = set()
    for cap in capabilities:
        entry = _capability_entry(cap)
        if entry is None:
            continue
        for host in entry.get("default_egress_hosts") or []:
            hosts.add(str(host).lower())
    return sorted(hosts)


def resolve_egress_allowlist(
    capabilities: list[str],
    override: list[str] | None,
) -> list[str]:
    if override is None:
        return default_egress_for_capabilities(capabilities)
    validate_egress_allowlist(override)
    return sorted({host.lower() for host in override})


def validate_egress_allowlist(hosts: list[str]) -> None:
    if not hosts:
        return
    invalid = [host for host in hosts if not _HOSTNAME_RE.match(host.strip().lower())]
    if invalid:
        raise ValueError(
            f"invalid egress allowlist hostnames: {', '.join(invalid)} "
            "(use bare hostnames like api.github.com or *.example.com)"
        )


def validate_egress_for_capabilities(
    capabilities: list[str],
    egress_allowlist: list[str] | None,
) -> None:
    required = capabilities_requiring_explicit_egress()
    if not required.intersection(capabilities):
        return
    if not egress_allowlist:
        missing = ", ".join(sorted(required.intersection(capabilities)))
        raise ValueError(
            f"capabilities [{missing}] require an explicit egress_allowlist at registration"
        )


def is_budget_exceeded_error(message: str) -> bool:
    return message.startswith("budget:")


def is_quarantine_error(message: str) -> bool:
    return message.startswith("quarantine:")
