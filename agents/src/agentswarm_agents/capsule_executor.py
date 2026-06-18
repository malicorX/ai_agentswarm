from __future__ import annotations



from typing import Any



from agentswarm_agents.coordinator_planner import build_deterministic_coordinator_plan

from agentswarm_agents.engineering_lab import apply_engineering_patch, run_fixture_tests

from agentswarm_agents.engineering_workspace import (

    execute_git_engineering_patch,

    run_git_workspace_tests,

    workspace_mode,

)

from agentswarm_agents.git_capsule import execute_git_patch_capsule
from agentswarm_agents.git_sandbox_executor import (
    execute_git_engineering_patch_sandbox,
    run_git_workspace_tests_sandbox,
)

from agentswarm_agents.sandbox_executor import run_compile_sandbox, run_fixture_tests_sandbox
from agentswarm_agents.windows_sandbox_executor import (
    run_compile_windows_vm,
    run_fixture_tests_windows_vm,
)


def _sandbox_spec(assignment: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(spec)
    task_id = assignment.get("task_id")
    if task_id:
        enriched["sandbox_run_id"] = str(task_id)
    return enriched





def _capsule_with_forge(assignment: dict[str, Any]) -> dict[str, Any]:
    capsule = dict(assignment.get("capsule") or {})
    forge = assignment.get("forge_credentials")
    if isinstance(forge, dict):
        capsule["forge_credentials"] = forge
    return capsule


def _git_in_container(assignment: dict[str, Any], capsule: dict[str, Any]) -> bool:
    if capsule.get("sandbox_git"):
        return True
    spec = capsule.get("verification_spec") or assignment.get("verification_spec")
    return isinstance(spec, dict) and bool(spec.get("git_in_container"))


def execute_capsule(assignment: dict[str, Any]) -> dict[str, Any]:

    """Run an assigned capsule in-process (mock LLM until local runtime is wired)."""

    task_type = assignment.get("task_type", "")

    capsule = _capsule_with_forge(assignment)

    if task_type == "coordinator.decompose":

        return build_deterministic_coordinator_plan(capsule)

    if task_type == "codewriter.patch":

        if isinstance(capsule.get("git"), dict) and isinstance(capsule.get("lab"), dict):

            goal_id = str(capsule.get("goal_id") or assignment.get("goal_id") or "")

            task_id = str(assignment.get("task_id") or "")

            if _git_in_container(assignment, capsule):
                spec = assignment.get("verification_spec")
                return execute_git_engineering_patch_sandbox(
                    capsule,
                    goal_id=goal_id,
                    task_id=task_id,
                    verification_spec=spec if isinstance(spec, dict) else None,
                )

            return execute_git_engineering_patch(

                capsule,

                goal_id=goal_id,

                task_id=task_id,

            )

        if isinstance(capsule.get("lab"), dict):

            return apply_engineering_patch(capsule)

        if isinstance(capsule.get("git"), dict):

            git_capsule = dict(capsule)

            git_capsule["task_id"] = assignment.get("task_id")

            return execute_git_patch_capsule(git_capsule)

        raise ValueError("codewriter.patch capsule requires lab or git section")

    if task_type == "builder.compile":
        spec = capsule.get("verification_spec") or assignment.get("verification_spec")
        if not isinstance(spec, dict):
            raise ValueError("builder.compile requires verification_spec")
        enriched = _sandbox_spec(assignment, spec)
        if workspace_mode(spec) == "windows":
            return run_compile_windows_vm(enriched)
        return run_compile_sandbox(enriched)

    if task_type == "tester.run":

        spec = capsule.get("verification_spec") or assignment.get("verification_spec")

        if isinstance(capsule.get("git"), dict):

            if _git_in_container(assignment, capsule):
                spec = capsule.get("verification_spec") or assignment.get("verification_spec")
                return run_git_workspace_tests_sandbox(
                    capsule,
                    verification_spec=spec if isinstance(spec, dict) else None,
                    task_id=str(assignment.get("task_id") or "") or None,
                )

            return run_git_workspace_tests(capsule)

        if isinstance(spec, dict):

            enriched = _sandbox_spec(assignment, spec)
            mode = workspace_mode(spec)
            if mode == "windows":
                return run_fixture_tests_windows_vm(enriched)
            if mode == "sandbox":
                return run_fixture_tests_sandbox(enriched)

            return run_fixture_tests(spec)

        return {"passed": True, "notes": "mock tester (no verification_spec)"}

    if task_type == "creative.text":

        brief = capsule.get("brief", "creative work")

        return {

            "text": (

                f"Container poem for: {brief}\n"

                "Sandboxed lines emerge,\n"

                "Docker holds the spark,\n"

                "Dispatch sends the work,\n"

                "Credits mark the arc."

            ),

        }

    if task_type == "reviewer.subjective":

        rubric = capsule.get("rubric") or [{"id": "quality", "weight": 1.0}]

        scores = {str(item["id"]): 8.0 for item in rubric}

        return {

            "scores": scores,

            "rationale": "Container reviewer: solid craft and on-brief.",

        }

    if task_type == "reviewer.approve":

        test_result = assignment.get("test_result")
        if not isinstance(test_result, dict):
            test_result = capsule.get("test_result")
        if isinstance(test_result, dict) and "passed" in test_result:
            approved = bool(test_result.get("passed"))
            return {
                "approved": approved,
                "notes": (
                    "auto-approved after passing tests"
                    if approved
                    else "tests failed"
                ),
            }

        return {"approved": True, "notes": "container approve"}

    return {"ok": True, "task_type": task_type}

