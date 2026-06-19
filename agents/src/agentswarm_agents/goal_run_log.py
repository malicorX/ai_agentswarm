"""Collect, analyze, and persist per-goal run diagnostics for operator debugging."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from agentswarm_agents.client_data_dir import client_data_dir
from agentswarm_agents.engineering_workspace import workspace_mode
from agentswarm_agents.replay_goal import (
    _workspace_ref,
    fetch_replay_context,
    list_workspace_tree,
    merge_trace_into_context,
)

TERMINAL_GOAL_STATUSES = frozenset({"verified", "rejected"})
DONE_STEP_STATUSES = frozenset(
    {"verified", "submitted", "passed", "approved", "failed", "rejected"}
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _repo_logs_dir() -> Path | None:
    override = os.environ.get("AGENTSWARM_REPO_ROOT", "").strip()
    if override:
        root = Path(override)
    else:
        return None
    if not (root / "platform").is_dir():
        return None
    path = root / "logs" / "goals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_log_paths(goal_id: str) -> list[Path]:
    paths = [client_data_dir() / "run-logs" / f"{goal_id}.json"]
    repo_dir = _repo_logs_dir()
    if repo_dir is not None:
        paths.append(repo_dir / f"{goal_id}.json")
    return paths


def fetch_goal_trace(base_url: str, goal_id: str) -> dict[str, Any]:
    clean = base_url.rstrip("/")
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(f"{clean}/creative/goals/{goal_id}/trace")
        if response.status_code == 404:
            raise ValueError(f"goal not found: {goal_id}")
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict):
        raise ValueError("trace response must be an object")
    return body


def load_replay_context(base_url: str, goal_id: str) -> dict[str, Any]:
    clean = base_url.rstrip("/")
    ctx = fetch_replay_context(clean, goal_id)
    try:
        trace = fetch_goal_trace(clean, goal_id)
    except (httpx.HTTPError, ValueError):
        trace = None
    return merge_trace_into_context(ctx, trace)


def _step_by_type(steps: list[dict[str, Any]], task_type: str) -> dict[str, Any] | None:
    for step in steps:
        if str(step.get("task_type")) == task_type:
            return step
    return None


def _step_result(step: dict[str, Any] | None) -> dict[str, Any]:
    if not step:
        return {}
    result = step.get("result")
    return dict(result) if isinstance(result, dict) else {}


def _step_done(step: dict[str, Any] | None) -> bool:
    if not step:
        return False
    status = str(step.get("status", "")).lower()
    return status in DONE_STEP_STATUSES or bool(step.get("submitted_at"))


def analyze_goal_run(
    trace: dict[str, Any],
    ctx: dict[str, Any],
    *,
    workspace_tree_error: str | None = None,
    outcome_error: str | None = None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    goal_id = str(trace.get("goal_id") or ctx.get("goal_id") or "")
    status = str(trace.get("status") or ctx.get("status") or "")
    steps = trace.get("steps") if isinstance(trace.get("steps"), list) else []
    spec = ctx.get("verification_spec")
    spec_dict = dict(spec) if isinstance(spec, dict) else {}
    mode = workspace_mode(spec_dict) if spec_dict else ""
    ws_ref = _workspace_ref(ctx)

    codewriter = _step_by_type(steps, "codewriter.patch")
    tester = _step_by_type(steps, "tester.run")
    reviewer = _step_by_type(steps, "reviewer.approve")

    if mode == "git" and _step_done(codewriter) and not ws_ref:
        issues.append(
            {
                "severity": "error",
                "code": "missing_workspace_ref",
                "message": (
                    "Git goal: codewriter finished but no workspace_ref on goal or steps. "
                    "Workspace replay/download will fail until the platform stores the commit SHA."
                ),
            }
        )

    reviewer_result = _step_result(reviewer)
    if _step_done(reviewer) and reviewer_result.get("approved") is True:
        if status not in TERMINAL_GOAL_STATUSES:
            issues.append(
                {
                    "severity": "error",
                    "code": "goal_stuck_after_reviewer",
                    "message": (
                        f"Reviewer approved but goal status is still {status or 'unknown'} "
                        "(expected verified)."
                    ),
                }
            )
    elif _step_done(tester) and _step_result(tester).get("passed") is True:
        if not _step_done(reviewer):
            issues.append(
                {
                    "severity": "warn",
                    "code": "awaiting_reviewer",
                    "message": "Tests passed; waiting for reviewer step to finish.",
                }
            )
        elif status not in TERMINAL_GOAL_STATUSES and reviewer_result.get("approved") is not True:
            issues.append(
                {
                    "severity": "warn",
                    "code": "reviewer_not_approved",
                    "message": "Reviewer step finished without approval.",
                }
            )

    if workspace_tree_error:
        issues.append(
            {
                "severity": "error",
                "code": "workspace_tree_failed",
                "message": workspace_tree_error,
            }
        )

    if outcome_error:
        issues.append(
            {
                "severity": "warn",
                "code": "outcome_bundle_failed",
                "message": outcome_error,
            }
        )

    if status in TERMINAL_GOAL_STATUSES and not issues:
        return issues

    active = trace.get("active_step")
    if status == "pending" and not active and not _step_done(reviewer):
        issues.append(
            {
                "severity": "warn",
                "code": "pipeline_in_progress",
                "message": "Goal is pending with no active step — volunteer may be idle or dispatch stalled.",
            }
        )

    return issues


def _compact_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for step in steps:
        compact.append(
            {
                "seq": step.get("seq"),
                "role": step.get("role"),
                "task_type": step.get("task_type"),
                "status": step.get("status"),
                "owner": step.get("owner"),
                "workspace_ref": step.get("workspace_ref"),
                "result_summary": step.get("result_summary"),
                "submitted_at": step.get("submitted_at"),
            }
        )
    return compact


def collect_goal_diagnostics(
    base_url: str,
    goal_id: str,
    *,
    include_workspace_probe: bool = True,
) -> dict[str, Any]:
    clean = base_url.rstrip("/")
    trace = fetch_goal_trace(clean, goal_id)
    ctx: dict[str, Any]
    replay_error: str | None = None
    try:
        ctx = load_replay_context(clean, goal_id)
    except (httpx.HTTPError, ValueError, PermissionError) as exc:
        replay_error = str(exc)
        ctx = merge_trace_into_context({"goal_id": goal_id}, trace)

    workspace_tree_error: str | None = None
    workspace_tree: dict[str, Any] | None = None
    if include_workspace_probe and str(trace.get("goal_kind", ctx.get("goal_kind"))) == "engineering":
        try:
            workspace_tree = list_workspace_tree(ctx)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            workspace_tree_error = str(exc)

    issues = analyze_goal_run(
        trace,
        ctx,
        workspace_tree_error=workspace_tree_error,
        outcome_error=replay_error,
    )

    return {
        "goal_id": goal_id,
        "api_url": clean,
        "collected_at": _utc_now_iso(),
        "goal_status": str(trace.get("status") or ""),
        "goal_kind": str(trace.get("goal_kind") or ctx.get("goal_kind") or ""),
        "workspace_ref": _workspace_ref(ctx),
        "workspace_mode": workspace_mode(spec)
        if isinstance(spec := ctx.get("verification_spec"), dict)
        else None,
        "issues": issues,
        "issue_count": len(issues),
        "has_errors": any(item["severity"] == "error" for item in issues),
        "trace_summary": {
            "active_step": trace.get("active_step"),
            "coordinator_task_id": trace.get("coordinator_task_id"),
            "step_count": len(trace.get("steps") or []),
        },
        "steps": _compact_steps(trace.get("steps") or []),
        "replay_context_error": replay_error,
        "workspace_tree_error": workspace_tree_error,
        "workspace_tree_mode": workspace_tree.get("mode") if workspace_tree else None,
    }


def write_goal_run_log(
    base_url: str,
    goal_id: str,
    *,
    include_workspace_probe: bool = True,
) -> tuple[dict[str, Any], list[Path]]:
    report = collect_goal_diagnostics(
        base_url,
        goal_id,
        include_workspace_probe=include_workspace_probe,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    written: list[Path] = []
    for path in run_log_paths(goal_id):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        written.append(path)
    return report, written


def format_goal_run_report(report: dict[str, Any]) -> str:
    lines = [
        f"Goal {report.get('goal_id')} @ {report.get('api_url')}",
        f"Status: {report.get('goal_status')}  workspace_ref: {report.get('workspace_ref') or '(none)'}",
        f"Collected: {report.get('collected_at')}",
        "",
    ]
    issues = report.get("issues") or []
    if not issues:
        lines.append("No issues detected.")
    else:
        lines.append(f"Issues ({len(issues)}):")
        for item in issues:
            lines.append(f"  [{item.get('severity', '?').upper()}] {item.get('code')}: {item.get('message')}")
    log_paths = run_log_paths(str(report.get("goal_id", "")))
    if log_paths:
        lines.extend(["", "Log files:"])
        for path in log_paths:
            lines.append(f"  {path}")
    return "\n".join(lines)
