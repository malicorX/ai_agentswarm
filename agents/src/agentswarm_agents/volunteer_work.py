"""Parse assignment/result metadata for volunteer UI and history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _capsule_dict(assignment: dict[str, Any]) -> dict[str, Any]:
    capsule = assignment.get("capsule")
    return dict(capsule) if isinstance(capsule, dict) else {}


def _goal_id_from_assignment(assignment: dict[str, Any]) -> str | None:
    for source in (assignment, _capsule_dict(assignment)):
        value = source.get("goal_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def role_from_assignment(assignment: dict[str, Any]) -> str:
    capability = assignment.get("capability_required")
    if isinstance(capability, str) and capability.strip():
        return capability.strip()
    task_type = str(assignment.get("task_type", "assignment"))
    return task_type.split(".", 1)[0]


def work_label_from_assignment(assignment: dict[str, Any]) -> str:
    capsule = _capsule_dict(assignment)
    brief = capsule.get("brief")
    if isinstance(brief, str) and brief.strip():
        return brief.strip()[:96]
    lab = capsule.get("lab")
    if isinstance(lab, dict):
        fixture = lab.get("fixture")
        if isinstance(fixture, str) and fixture.strip():
            return f"fixture:{fixture.strip()}"
    git = capsule.get("git")
    if isinstance(git, dict):
        repo_url = git.get("repo_url")
        if isinstance(repo_url, str) and repo_url.strip():
            tail = repo_url.strip().rstrip("/").split("/")[-1]
            return tail or repo_url.strip()[:48]
    task_id = assignment.get("task_id")
    if isinstance(task_id, str) and task_id.strip():
        return task_id.strip()
    return "assignment"


@dataclass(frozen=True)
class VolunteerWorkContext:
    task_id: str
    task_type: str
    role: str
    goal_id: str | None
    project_id: str | None
    label: str

    @property
    def goal_display(self) -> str:
        return self.goal_id or "—"

    @property
    def project_display(self) -> str:
        return self.project_id or "—"


def work_context_from_assignment(assignment: dict[str, Any]) -> VolunteerWorkContext:
    task_id = str(assignment.get("task_id") or "unknown")
    task_type = str(assignment.get("task_type") or "assignment")
    project_id = assignment.get("project_id")
    return VolunteerWorkContext(
        task_id=task_id,
        task_type=task_type,
        role=role_from_assignment(assignment),
        goal_id=_goal_id_from_assignment(assignment),
        project_id=str(project_id).strip() if isinstance(project_id, str) and project_id.strip() else None,
        label=work_label_from_assignment(assignment),
    )


def running_status_detail(context: VolunteerWorkContext) -> str:
    parts = [context.role, context.task_type]
    if context.goal_id:
        parts.append(context.goal_id)
    parts.append(context.task_id)
    return " · ".join(parts)


@dataclass(frozen=True)
class VolunteerWorkEvent:
    kind: Literal["started", "finished"]
    context: VolunteerWorkContext
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["running", "ok", "error"] = "running"
    submission_id: str | None = None
    summary: str = ""
    detail: str = ""


def summarize_work_result(task_type: str, result: dict[str, Any]) -> tuple[str, str]:
    """Return a one-line summary and a longer detail block."""
    lines: list[str] = []
    summary = "completed"

    if task_type == "creative.text":
        text = result.get("text")
        if isinstance(text, str) and text.strip():
            preview = " ".join(text.strip().split())[:120]
            summary = f"text: {preview}"
            lines.append(text.strip())
    elif task_type == "codewriter.patch":
        if result.get("applied"):
            file_path = result.get("file")
            artifact = result.get("git_artifact")
            if isinstance(artifact, dict):
                branch = artifact.get("branch")
                sha = artifact.get("commit_sha")
                summary = f"patched {file_path or 'file'} → {branch or 'branch'}"
                if sha:
                    lines.append(f"commit: {sha}")
            else:
                summary = f"patched {file_path or 'file'}"
            workspace_ref = result.get("workspace_ref")
            if workspace_ref:
                lines.append(f"workspace_ref: {workspace_ref}")
        else:
            summary = "patch not applied"
    elif task_type == "tester.run":
        passed = result.get("passed")
        if passed is True:
            summary = "tests passed"
        elif passed is False:
            summary = "tests failed"
            for key in ("stderr", "stdout", "error"):
                chunk = result.get(key)
                if isinstance(chunk, str) and chunk.strip():
                    lines.append(f"{key}:\n{chunk.strip()[-3000:]}")
        else:
            summary = "tests finished"
    elif task_type == "reviewer.subjective":
        scores = result.get("scores")
        if isinstance(scores, dict) and scores:
            score_text = ", ".join(f"{k}={v}" for k, v in scores.items())
            summary = f"scores: {score_text}"
        rationale = result.get("rationale")
        if isinstance(rationale, str) and rationale.strip():
            lines.append(rationale.strip())
    elif task_type == "coordinator.decompose":
        needs = result.get("pool_needs")
        count = len(needs) if isinstance(needs, list) else 0
        summary = f"planned {count} pool need(s)"
    elif task_type == "builder.compile":
        if result.get("success"):
            summary = "build succeeded"
        else:
            summary = "build failed"
            for key in ("stdout", "stderr", "error"):
                chunk = result.get(key)
                if isinstance(chunk, str) and chunk.strip():
                    lines.append(f"{key}:\n{chunk.strip()}")

    if not lines:
        for key in ("stdout", "stderr", "error", "message"):
            chunk = result.get(key)
            if isinstance(chunk, str) and chunk.strip():
                lines.append(chunk.strip())
                break
    if not lines and result:
        lines.append(str(result)[:2000])
    return summary, "\n\n".join(lines)


def started_event(context: VolunteerWorkContext) -> VolunteerWorkEvent:
    now = _utc_now()
    return VolunteerWorkEvent(
        kind="started",
        context=context,
        started_at=now,
        status="running",
        summary=context.label,
    )


def finished_event(
    context: VolunteerWorkContext,
    *,
    started_at: datetime,
    status: Literal["ok", "error"],
    submission_id: str | None,
    summary: str,
    detail: str,
) -> VolunteerWorkEvent:
    return VolunteerWorkEvent(
        kind="finished",
        context=context,
        started_at=started_at,
        finished_at=_utc_now(),
        status=status,
        submission_id=submission_id,
        summary=summary,
        detail=detail,
    )
