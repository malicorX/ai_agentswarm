"""Route volunteer assignments to host vs Docker worker executors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.docker_worker import run_capsule_in_docker
from agentswarm_agents.engineering_workspace import workspace_mode
from agentswarm_agents.worker_llm import engineering_llm_enabled

CapsuleExecutor = Callable[[dict[str, Any]], dict[str, Any]]


def _capsule_dict(assignment: dict[str, Any]) -> dict[str, Any]:
    capsule = assignment.get("capsule")
    return dict(capsule) if isinstance(capsule, dict) else {}


def _verification_spec(assignment: dict[str, Any], capsule: dict[str, Any]) -> dict[str, Any]:
    spec = assignment.get("verification_spec") or capsule.get("verification_spec")
    return dict(spec) if isinstance(spec, dict) else {}


def _git_in_container(assignment: dict[str, Any], capsule: dict[str, Any]) -> bool:
    if capsule.get("sandbox_git"):
        return True
    spec = _verification_spec(assignment, capsule)
    return bool(spec.get("git_in_container"))


def assignment_needs_host_executor(assignment: dict[str, Any]) -> bool:
    """Git/sandbox engineering must run on the volunteer host (nested Docker / git / pilot)."""
    task_type = str(assignment.get("task_type", ""))
    capsule = _capsule_dict(assignment)
    spec = _verification_spec(assignment, capsule)
    mode = workspace_mode(spec) if spec else "local_fixture"

    if task_type == "codewriter.patch":
        if isinstance(capsule.get("git"), dict):
            return True
        if isinstance(capsule.get("lab"), dict):
            return True

    if task_type == "builder.compile":
        return mode in ("sandbox", "windows")

    if task_type == "tester.run":
        if isinstance(capsule.get("git"), dict):
            return True
        if mode in ("sandbox", "windows", "local_fixture"):
            return True
        if spec.get("fixture"):
            return True
        if _git_in_container(assignment, capsule):
            return True

    return False


def _infer_engineering_insert(
    assignment: dict[str, Any],
    *,
    agent_id: str,
    model_path: Path | None,
    model_entry: dict[str, Any] | None,
    worker_image: str,
) -> str:
    infer_assignment = {
        "task_type": "engineering.infer_patch",
        "capsule": _capsule_dict(assignment),
        "goal_id": assignment.get("goal_id"),
    }
    result = run_capsule_in_docker(
        infer_assignment,
        agent_id=agent_id,
        image=worker_image,
        model_path=model_path,
        model_entry=model_entry,
    )
    insert = result.get("insert")
    if not isinstance(insert, str) or not insert.strip():
        raise RuntimeError("engineering LLM did not return patch insert text")
    return insert.strip()


def execute_assignment_on_host(
    assignment: dict[str, Any],
    *,
    agent_id: str,
    model_path: Path | None = None,
    model_entry: dict[str, Any] | None = None,
    worker_image: str = "agentswarm-worker:dev",
) -> dict[str, Any]:
    task_type = str(assignment.get("task_type", ""))
    capsule = _capsule_dict(assignment)

    if (
        task_type == "codewriter.patch"
        and engineering_llm_enabled()
        and model_path is not None
        and isinstance(capsule.get("git"), dict)
        and isinstance(capsule.get("patch"), dict)
    ):
        insert = _infer_engineering_insert(
            assignment,
            agent_id=agent_id,
            model_path=model_path,
            model_entry=model_entry,
            worker_image=worker_image,
        )
        enriched = dict(assignment)
        enriched_capsule = dict(capsule)
        enriched_capsule["patch"] = {**capsule["patch"], "insert": insert}
        enriched["capsule"] = enriched_capsule
        return execute_capsule(enriched)

    return execute_capsule(assignment)


def resolve_hybrid_docker_executor(
    agent_id: str,
    *,
    model_entry: dict[str, Any],
    default_image: str,
    model_path: Path | None,
    docker_executor: CapsuleExecutor,
) -> CapsuleExecutor:
    worker_image = default_image

    def _executor(assignment: dict[str, Any]) -> dict[str, Any]:
        if assignment_needs_host_executor(assignment):
            return execute_assignment_on_host(
                assignment,
                agent_id=agent_id,
                model_path=model_path,
                model_entry=model_entry,
                worker_image=worker_image,
            )
        return docker_executor(assignment)

    return _executor
