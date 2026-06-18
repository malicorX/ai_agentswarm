"""Normalize goal trace + replay context into format-agnostic deliverables."""

from __future__ import annotations

from typing import Any

OutcomeDeliverable = dict[str, Any]
OutcomeBundle = dict[str, Any]

_KNOWN_ACTIONS = frozenset(
    {
        "view_text",
        "view_files",
        "download_zip",
        "verify",
        "view_blob",
        "inspect_json",
    }
)


def _clip(text: str, limit: int = 280) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _append_deliverable(
    items: list[OutcomeDeliverable],
    *,
    kind: str,
    label: str,
    source_step: str | None = None,
    preview: str | None = None,
    ref: str | None = None,
    actions: list[str] | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    action_list = [action for action in (actions or []) if action in _KNOWN_ACTIONS]
    items.append(
        {
            "id": f"{kind}-{len(items) + 1}",
            "kind": kind,
            "label": label,
            "source_step": source_step,
            "preview": preview,
            "ref": ref,
            "actions": action_list,
            "detail": detail or {},
        }
    )


def _blob_refs_from_result(result: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()

    def add(raw: Any) -> None:
        if not isinstance(raw, str):
            return
        cleaned = raw.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            refs.append(cleaned)

    add(result.get("artifact_ref"))
    for nested_key in ("run_artifact", "build_artifact"):
        nested = result.get(nested_key)
        if isinstance(nested, dict):
            add(nested.get("artifact_ref"))
            add(nested.get("log_artifact_ref"))
    return refs


def _summary_for_status(status: str, *, deliverable_count: int, role_count: int) -> str:
    normalized = status.strip().lower()
    if normalized == "verified":
        return f"Goal verified with {deliverable_count} deliverable(s) across {role_count} pipeline step(s)."
    if normalized == "rejected":
        return f"Goal rejected — inspect deliverables and step evidence ({role_count} step(s))."
    if normalized == "pending":
        return f"Goal in progress ({role_count} step(s) recorded so far)."
    return f"Goal status={status or 'unknown'} ({deliverable_count} deliverable(s))."


def build_outcome_bundle(
    trace: dict[str, Any],
    *,
    replay_context: dict[str, Any] | None = None,
) -> OutcomeBundle:
    """Build a task-agnostic view of what the swarm produced for this goal."""
    ctx = replay_context or {}
    goal_id = str(trace.get("goal_id") or ctx.get("goal_id") or "")
    status = str(trace.get("status") or ctx.get("status") or "")
    goal_kind = str(trace.get("goal_kind") or ctx.get("goal_kind") or "creative")
    brief = str(trace.get("brief") or ctx.get("brief") or "")
    steps = trace.get("steps") or []
    deliverables: list[OutcomeDeliverable] = []

    artifact_text = trace.get("artifact_text") or ctx.get("artifact_text")
    if isinstance(artifact_text, str) and artifact_text.strip():
        _append_deliverable(
            deliverables,
            kind="text",
            label="Creative deliverable",
            preview=_clip(artifact_text),
            actions=["view_text"],
            detail={"text": artifact_text},
        )

    workspace_ref = trace.get("workspace_ref") or ctx.get("workspace_ref")
    if isinstance(workspace_ref, str) and workspace_ref.strip():
        ws = trace.get("code_workspace") if isinstance(trace.get("code_workspace"), dict) else {}
        spec = ctx.get("verification_spec")
        mode = str(
            ws.get("mode")
            or (spec.get("workspace_mode") if isinstance(spec, dict) else None)
            or "workspace"
        )
        _append_deliverable(
            deliverables,
            kind="git_workspace",
            label=f"Code workspace ({mode})",
            ref=workspace_ref.strip(),
            preview=f"commit/workspace ref {workspace_ref.strip()[:12]}…",
            actions=["view_files", "download_zip", "verify"],
            detail={"workspace_mode": mode},
        )

    for step in steps:
        if not isinstance(step, dict):
            continue
        role = str(step.get("role") or step.get("task_type") or "step")
        task_type = str(step.get("task_type") or "")
        result = step.get("result")
        if not isinstance(result, dict):
            continue

        if task_type == "reviewer.approve" or "approved" in result:
            approved = result.get("approved")
            notes = str(result.get("notes") or "")
            _append_deliverable(
                deliverables,
                kind="approval",
                label="Reviewer verdict",
                source_step=role,
                preview=f"approved={approved}" + (f" — {notes}" if notes else ""),
                actions=["inspect_json"],
                detail={"approved": approved, "notes": notes},
            )

        scores = result.get("scores")
        if isinstance(scores, dict) and scores:
            score_text = ", ".join(f"{key}={value}" for key, value in scores.items())
            _append_deliverable(
                deliverables,
                kind="scores",
                label="Reviewer scores",
                source_step=role,
                preview=score_text,
                actions=["inspect_json"],
                detail={"scores": scores, "rationale": result.get("rationale")},
            )

        for ref in _blob_refs_from_result(result):
            _append_deliverable(
                deliverables,
                kind="blob",
                label=f"Stored artifact ({role})",
                source_step=role,
                ref=ref,
                preview=ref[:48] + ("…" if len(ref) > 48 else ""),
                actions=["view_blob"],
            )

        stdout = result.get("stdout")
        stderr = result.get("stderr")
        if isinstance(stdout, str) and stdout.strip():
            _append_deliverable(
                deliverables,
                kind="logs",
                label=f"stdout ({role})",
                source_step=role,
                preview=_clip(stdout, 200),
                actions=["inspect_json"],
                detail={"stream": "stdout", "text": stdout[-8000:]},
            )
        if isinstance(stderr, str) and stderr.strip():
            _append_deliverable(
                deliverables,
                kind="logs",
                label=f"stderr ({role})",
                source_step=role,
                preview=_clip(stderr, 200),
                actions=["inspect_json"],
                detail={"stream": "stderr", "text": stderr[-8000:]},
            )

        if "passed" in result:
            passed = result.get("passed")
            _append_deliverable(
                deliverables,
                kind="verification",
                label=f"Test result ({role})",
                source_step=role,
                preview=f"passed={passed}",
                actions=["verify", "inspect_json"],
                detail={"passed": passed, "returncode": result.get("returncode")},
            )

        text = result.get("text")
        if isinstance(text, str) and text.strip() and task_type == "creative.text":
            _append_deliverable(
                deliverables,
                kind="text",
                label="Creative text output",
                source_step=role,
                preview=_clip(text),
                actions=["view_text"],
                detail={"text": text},
            )

        if task_type == "coordinator.decompose":
            needs = result.get("pool_needs")
            deferred = result.get("deferred_pool_needs")
            count = len(needs) if isinstance(needs, list) else 0
            defer_count = len(deferred) if isinstance(deferred, list) else 0
            _append_deliverable(
                deliverables,
                kind="plan",
                label="Coordinator plan",
                source_step=role,
                preview=f"{count} immediate + {defer_count} deferred pool needs",
                actions=["inspect_json"],
                detail={"pool_needs": needs, "deferred_pool_needs": deferred},
            )

        if result.get("applied") is not None and task_type == "codewriter.patch":
            file_path = result.get("file") or (result.get("patch") or {}).get("file")
            _append_deliverable(
                deliverables,
                kind="patch",
                label="Codewriter patch",
                source_step=role,
                preview=f"applied={result.get('applied')} file={file_path or '?'}",
                actions=["inspect_json", "view_files"],
                detail=result,
            )

    primary = trace.get("primary_artifact_ref")
    artifact_refs = trace.get("artifact_refs") or []
    if isinstance(primary, str) and primary.strip():
        if not any(item.get("ref") == primary for item in deliverables):
            _append_deliverable(
                deliverables,
                kind="blob",
                label="Primary deploy artifact",
                ref=primary.strip(),
                preview=primary.strip(),
                actions=["view_blob"],
            )
    if isinstance(artifact_refs, list):
        for ref in artifact_refs:
            if not isinstance(ref, str) or not ref.strip():
                continue
            if any(item.get("ref") == ref for item in deliverables):
                continue
            _append_deliverable(
                deliverables,
                kind="blob",
                label="Goal artifact ref",
                ref=ref.strip(),
                preview=ref.strip(),
                actions=["view_blob"],
            )

    roles = [
        str(step.get("role"))
        for step in steps
        if isinstance(step, dict) and step.get("role")
    ]
    return {
        "goal_id": goal_id,
        "status": status,
        "goal_kind": goal_kind,
        "brief": brief,
        "summary": _summary_for_status(
            status,
            deliverable_count=len(deliverables),
            role_count=len(roles),
        ),
        "pipeline_roles": roles,
        "deliverables": deliverables,
        "artifact_refs": list(artifact_refs) if isinstance(artifact_refs, list) else [],
        "primary_artifact_ref": primary if isinstance(primary, str) else None,
        "workspace_ref": workspace_ref if isinstance(workspace_ref, str) else None,
    }
