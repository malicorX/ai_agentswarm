from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModerationPolicy:
    canary_failure_rate_threshold: float = 0.5
    min_canary_attempts: int = 2
    flag_deploy_backlog: bool = True
    max_agents_per_owner: int = 0


def resolve_moderation_policy(governance_config: dict[str, Any] | None) -> ModerationPolicy:
    moderation = (governance_config or {}).get("moderation") or {}
    if not isinstance(moderation, dict):
        return ModerationPolicy()
    threshold = moderation.get("canary_failure_rate_threshold", 0.5)
    min_attempts = moderation.get("min_canary_attempts", 2)
    try:
        resolved_threshold = float(threshold)
    except (TypeError, ValueError):
        resolved_threshold = 0.5
    try:
        resolved_attempts = int(min_attempts)
    except (TypeError, ValueError):
        resolved_attempts = 2
    flag_deploy = moderation.get("flag_deploy_backlog", True)
    max_per_owner = moderation.get("max_agents_per_owner", 0)
    try:
        resolved_max_per_owner = int(max_per_owner)
    except (TypeError, ValueError):
        resolved_max_per_owner = 0
    return ModerationPolicy(
        canary_failure_rate_threshold=max(0.0, min(1.0, resolved_threshold)),
        min_canary_attempts=max(1, resolved_attempts),
        flag_deploy_backlog=bool(flag_deploy),
        max_agents_per_owner=max(0, resolved_max_per_owner),
    )


def build_moderation_actions(
    summary: dict[str, Any],
    policy: ModerationPolicy | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved = policy or ModerationPolicy()
    findings: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    for entry in summary.get("canary_failures_top") or []:
        attempts = int(entry.get("attempts", 0))
        failures = int(entry.get("failures", 0))
        if attempts < resolved.min_canary_attempts:
            continue
        failure_rate = failures / attempts
        agent_id = entry["agent_id"]
        if failure_rate >= resolved.canary_failure_rate_threshold:
            findings.append(
                {
                    "type": "canary_failure_rate",
                    "agent_id": agent_id,
                    "failure_rate": round(failure_rate, 3),
                    "attempts": attempts,
                }
            )
            actions.append(
                {
                    "type": "quarantine",
                    "agent_id": agent_id,
                    "reason": (
                        f"canary failure rate {failure_rate:.0%} over {attempts} attempts "
                        f"(threshold {resolved.canary_failure_rate_threshold:.0%})"
                    ),
                }
            )
        elif failures > 0:
            findings.append(
                {
                    "type": "canary_failures",
                    "agent_id": agent_id,
                    "failures": failures,
                }
            )
            actions.append(
                {
                    "type": "flag",
                    "subject_type": "agent",
                    "subject_id": agent_id,
                    "reason": "elevated canary failures",
                    "severity": "medium",
                    "details": entry,
                }
            )

    disputed = int(summary.get("replication_groups", {}).get("disputed", 0))
    if disputed > 0:
        findings.append({"type": "disputed_replications", "count": disputed})
        actions.append(
            {
                "type": "flag",
                "subject_type": "platform",
                "subject_id": "replication",
                "reason": f"{disputed} disputed replication group(s) need review",
                "severity": "medium",
                "details": {"disputed_count": disputed},
            }
        )

    if resolved.flag_deploy_backlog:
        deploy = summary.get("deploy_requests") or {}
        by_status = deploy.get("by_status") or {}
        pending_requests = int(by_status.get("pending", 0))
        pending_signoff_tasks = int(deploy.get("pending_signoff_tasks", 0))
        if pending_requests > 0 or pending_signoff_tasks > 0:
            findings.append(
                {
                    "type": "pending_deploy_signoffs",
                    "pending_requests": pending_requests,
                    "open_signoff_tasks": pending_signoff_tasks,
                }
            )
            actions.append(
                {
                    "type": "flag",
                    "subject_type": "platform",
                    "subject_id": "deploy",
                    "reason": (
                        f"{pending_requests} deploy request(s) awaiting sign-off "
                        f"({pending_signoff_tasks} open approve task(s))"
                    ),
                    "severity": "medium",
                    "details": {
                        "pending_requests": pending_requests,
                        "open_signoff_tasks": pending_signoff_tasks,
                    },
                }
            )

        approved_waiting = int(by_status.get("approved", 0))
        pending_execute_tasks = int(deploy.get("pending_execute_tasks", 0))
        if approved_waiting > 0 and pending_execute_tasks > 0:
            findings.append(
                {
                    "type": "pending_deploy_execute",
                    "approved_requests": approved_waiting,
                    "open_execute_tasks": pending_execute_tasks,
                }
            )
            actions.append(
                {
                    "type": "flag",
                    "subject_type": "platform",
                    "subject_id": "deploy",
                    "reason": (
                        f"{approved_waiting} approved deploy(s) waiting for execution "
                        f"({pending_execute_tasks} open execute task(s))"
                    ),
                    "severity": "medium",
                    "details": {
                        "approved_requests": approved_waiting,
                        "open_execute_tasks": pending_execute_tasks,
                    },
                }
            )

    if resolved.max_agents_per_owner > 0:
        for cluster in summary.get("owner_clusters") or []:
            count = int(cluster.get("agent_count", 0))
            owner = str(cluster.get("owner", ""))
            if count < resolved.max_agents_per_owner or not owner:
                continue
            findings.append(
                {
                    "type": "owner_agent_cluster",
                    "owner": owner,
                    "agent_count": count,
                }
            )
            actions.append(
                {
                    "type": "flag",
                    "subject_type": "owner",
                    "subject_id": owner,
                    "reason": (
                        f"owner {owner!r} has {count} registered agents "
                        f"(threshold {resolved.max_agents_per_owner})"
                    ),
                    "severity": "medium",
                    "details": cluster,
                }
            )

    return findings, actions
