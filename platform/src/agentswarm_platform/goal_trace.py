from __future__ import annotations

from typing import Any

ROLE_ORDER: dict[str, int] = {
    "coordinator.decompose": 0,
    "codewriter.patch": 1,
    "builder.compile": 2,
    "creative.text": 1,
    "tester.run": 3,
    "reviewer.subjective": 4,
    "reviewer.approve": 4,
}

ROLE_LABELS: dict[str, str] = {
    "coordinator.decompose": "coordinator",
    "codewriter.patch": "codewriter",
    "builder.compile": "builder",
    "creative.text": "creative",
    "tester.run": "tester",
    "reviewer.approve": "reviewer",
    "reviewer.subjective": "reviewer",
}

PIPELINE_PHASES: dict[str, str] = {
    "coordinator.decompose": "plan",
    "codewriter.patch": "code",
    "builder.compile": "build",
    "creative.text": "code",
    "tester.run": "test",
    "reviewer.approve": "review",
    "reviewer.subjective": "review",
}


def pipeline_phase(task_type: str) -> str:
    return PIPELINE_PHASES.get(task_type, task_type.split(".", 1)[0])


def role_label(task_type: str) -> str:
    return ROLE_LABELS.get(task_type, task_type.split(".", 1)[0])


def summarize_task_result(task_type: str, result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    if task_type == "coordinator.decompose":
        needs = result.get("pool_needs") or []
        deferred = result.get("deferred_pool_needs") or []
        return f"planned {len(needs)} immediate + {len(deferred)} deferred pool needs"
    if task_type == "codewriter.patch":
        applied = result.get("applied")
        patch = result.get("patch") or result.get("capsule", {}).get("patch") or {}
        target = patch.get("file") or patch.get("path") or result.get("file") or "patch"
        ref = result.get("workspace_ref")
        ref_suffix = f" ref={ref[:12]}…" if isinstance(ref, str) and len(ref) > 12 else (
            f" ref={ref}" if ref else ""
        )
        return f"applied={applied} target={target}{ref_suffix}"
    if task_type == "builder.compile":
        passed = result.get("passed")
        build = result.get("build_artifact") or {}
        digest = build.get("stdout_digest", "")
        digest_suffix = f" digest={digest[:12]}…" if digest else ""
        owner = result.get("sandbox_host_owner") or build.get("sandbox_host_owner")
        owner_suffix = f" host={owner}" if owner else ""
        return f"passed={passed} sandbox=true{owner_suffix}{digest_suffix}"
    if task_type == "tester.run":
        passed = result.get("passed")
        if result.get("sandbox"):
            digest = (result.get("run_artifact") or {}).get("stdout_digest", "")
            digest_suffix = f" digest={digest[:12]}…" if digest else ""
            owner = result.get("sandbox_host_owner") or (result.get("run_artifact") or {}).get(
                "sandbox_host_owner"
            )
            owner_suffix = f" host={owner}" if owner else ""
            log_ref = (result.get("run_artifact") or {}).get("log_artifact_ref")
            log_suffix = f" log={log_ref[:20]}…" if isinstance(log_ref, str) and len(log_ref) > 20 else (
                f" log={log_ref}" if log_ref else ""
            )
            return f"passed={passed} sandbox=true{owner_suffix}{digest_suffix}{log_suffix}"
        ref = result.get("workspace_ref")
        ref_suffix = f" ref={ref[:12]}…" if isinstance(ref, str) and len(ref) > 12 else (
            f" ref={ref}" if ref else ""
        )
        command = result.get("command") or result.get("cmd") or ""
        suffix = f" ({command})" if command else ref_suffix
        return f"passed={passed}{suffix}"
    if task_type in ("reviewer.approve", "reviewer.subjective"):
        if "approved" in result:
            return f"approved={result.get('approved')}"
        scores = result.get("scores")
        if isinstance(scores, dict):
            return f"scores={scores}"
        return str(result.get("rationale", ""))[:120]
    if task_type == "creative.text":
        text = str(result.get("text", ""))
        preview = text[:120] + ("…" if len(text) > 120 else "")
        return preview
    return str(result)[:160]


def describe_task_work(task_type: str, payload: dict[str, Any] | None) -> str:
    """Human-readable description of what this role is doing for the goal."""
    payload = payload or {}
    capsule = payload.get("capsule") if isinstance(payload.get("capsule"), dict) else payload
    brief = str(payload.get("brief") or capsule.get("brief") or "")[:120]

    if task_type == "coordinator.decompose":
        suffix = f" — brief: {brief}" if brief else ""
        return f"Plan the work chain (codewriter → tester → reviewer){suffix}"

    if task_type == "codewriter.patch":
        git = capsule.get("git") if isinstance(capsule.get("git"), dict) else {}
        patch = capsule.get("patch") if isinstance(capsule.get("patch"), dict) else {}
        if git:
            repo = git.get("repo_url", "git repo")
            target = patch.get("file", "file")
            return f"Clone {repo}, patch {target}, push agentswarm/goal-<id> branch"
        lab = capsule.get("lab") if isinstance(capsule.get("lab"), dict) else {}
        if lab:
            fixture = lab.get("fixture", "primes")
            target = patch.get("file", f"{fixture}.py")
            return (
                f"Implement code in pilot/engineering-lab/{fixture}/{target} "
                f"on the worker machine (local AGENTSWARM_REPO_ROOT)"
            )
        return "Apply codewriter patch to project files"

    if task_type == "builder.compile":
        spec = payload.get("verification_spec") or capsule.get("verification_spec") or {}
        fixture = spec.get("fixture", "primes") if isinstance(spec, dict) else "primes"
        if isinstance(spec, dict) and spec.get("workspace_mode") == "windows":
            return (
                f"Compile-check engineering-lab/{fixture} inside Windows VM "
                f"(sandbox.windows, python -m compileall)"
            )
        return (
            f"Compile-check engineering-lab/{fixture} inside Docker "
            f"(sandbox.linux, python -m compileall)"
        )

    if task_type == "tester.run":
        git = capsule.get("git") if isinstance(capsule.get("git"), dict) else {}
        workspace_ref = payload.get("workspace_ref") or capsule.get("workspace_ref")
        if git:
            ref = workspace_ref or "pending"
            return f"Clone {git.get('repo_url', 'git repo')} @ {ref} and run pytest"
        spec = payload.get("verification_spec") or capsule.get("verification_spec") or {}
        if isinstance(spec, dict) and spec.get("workspace_mode") == "windows":
            fixture = spec.get("fixture", "primes")
            return (
                f"Run pytest on engineering-lab/{fixture} inside Windows VM "
                f"(sandbox.windows, Hyper-V pool)"
            )
        if isinstance(spec, dict) and spec.get("workspace_mode") == "sandbox":
            fixture = spec.get("fixture", "primes")
            return (
                f"Run pytest on engineering-lab/{fixture} inside Docker "
                f"(sandbox.linux, --network=none)"
            )
        if isinstance(spec, dict) and spec.get("fixture"):
            return f"Run pytest on engineering-lab fixture {spec.get('fixture')}"
        return "Run automated tests on the submission"

    if task_type == "reviewer.approve":
        return "Review test results and approve or reject the engineering goal"

    if task_type == "reviewer.subjective":
        return "Score creative output against the goal rubric"

    if task_type == "creative.text":
        return f"Write creative artifact{f': {brief}' if brief else ''}"

    return f"Execute {task_type}"


def workspace_ref_for_step(
    task_type: str,
    payload: dict[str, Any] | None,
    result: dict[str, Any] | None,
) -> str | None:
    """Extract git/workspace commit ref from a pipeline step when present."""
    if isinstance(result, dict):
        ref = result.get("workspace_ref")
        if isinstance(ref, str) and ref.strip():
            return ref.strip()
        git_artifact = result.get("git_artifact")
        if isinstance(git_artifact, dict):
            commit = git_artifact.get("commit_sha")
            if isinstance(commit, str) and commit.strip():
                return commit.strip()
    payload = payload or {}
    for key in ("workspace_ref",):
        ref = payload.get(key)
        if isinstance(ref, str) and ref.strip():
            return ref.strip()
    capsule = payload.get("capsule")
    if isinstance(capsule, dict):
        ref = capsule.get("workspace_ref")
        if isinstance(ref, str) and ref.strip():
            return ref.strip()
        parent = capsule.get("parent_git_artifact")
        if isinstance(parent, dict):
            commit = parent.get("commit_sha")
            if isinstance(commit, str) and commit.strip():
                return commit.strip()
    return None


def sandbox_host_for_step(result: dict[str, Any] | None) -> str | None:
    if not isinstance(result, dict):
        return None
    owner = result.get("sandbox_host_owner")
    if isinstance(owner, str) and owner.strip():
        return owner.strip()
    for key in ("run_artifact", "build_artifact"):
        nested = result.get(key)
        if isinstance(nested, dict):
            nested_owner = nested.get("sandbox_host_owner")
            if isinstance(nested_owner, str) and nested_owner.strip():
                return nested_owner.strip()
    return None


def log_artifact_ref_for_step(result: dict[str, Any] | None) -> str | None:
    if not isinstance(result, dict):
        return None
    for key in ("run_artifact", "build_artifact"):
        nested = result.get(key)
        if isinstance(nested, dict):
            ref = nested.get("log_artifact_ref")
            if isinstance(ref, str) and ref.strip():
                return ref.strip()
    return None


def engineering_code_workspace(
    verification_spec: dict[str, Any] | None,
    *,
    workspace: dict[str, Any] | None = None,
    workspace_ref: str | None = None,
) -> dict[str, str]:
    spec = verification_spec or {}
    mode = str(spec.get("workspace_mode", "local_fixture"))
    if workspace and workspace.get("mode") == "git":
        mode = "git"
    fixture = str(spec.get("fixture", "primes"))
    if mode == "sandbox":
        return {
            "mode": "sandbox",
            "path": f"pilot/engineering-lab/{fixture}",
            "sharing": (
                "Codewriter patches the local fixture checkout; tester runs pytest "
                "inside an ephemeral Docker container (--network=none). Requires Docker "
                "on volunteers advertising sandbox.linux."
            ),
        }
    if mode == "windows":
        return {
            "mode": "windows",
            "path": f"pilot/engineering-lab/{fixture}",
            "sharing": (
                "Codewriter patches the local fixture checkout; builder and tester run "
                "inside an isolated Windows VM (Hyper-V pool). Volunteers advertise "
                "sandbox.windows.build / sandbox.windows.test — never run .exe on bare metal."
            ),
        }
    if mode == "git":
        repo = str((workspace or {}).get("repo_url", "git repository"))
        ref = workspace_ref or "(set after codewriter commit)"
        return {
            "mode": "git",
            "path": repo,
            "sharing": (
                f"Goal-scoped branch agentswarm/goal-<id>; workspace_ref={ref}. "
                "Distributed handoff via git push/pull, not shared host paths."
            ),
        }
    return {
        "mode": "local_fixture",
        "path": f"pilot/engineering-lab/{fixture}",
        "sharing": (
            "Workers started together (start_task) share one checkout via "
            "AGENTSWARM_REPO_ROOT on that machine. Remote machines do not "
            "see each other's files unless you add git sync or a shared volume."
        ),
    }
