"""Parse task definition files for create_task."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentswarm_agents.engineering_lab import list_fixtures

DEFAULT_GOAL_KIND = "engineering"
DEFAULT_FIXTURE = "primes"
DEFAULT_PROJECT_ID = "default"
DEFAULT_CREATIVE_RUBRIC = [
    {"id": "quality", "weight": 1.0, "description": "Overall craft"},
]

_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})
_BOOL_FALSE = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class TaskSpec:
    brief: str
    goal_kind: str = DEFAULT_GOAL_KIND
    fixture: str = DEFAULT_FIXTURE
    lab: str = "engineering-lab"
    project_id: str = DEFAULT_PROJECT_ID
    min_reviewers: int | None = None
    pass_threshold: float | None = None
    dispatch_isolated: bool = False
    dispatch_include_owners: list[str] | None = None
    workspace_mode: str = "local_fixture"
    workspace_repo_url: str | None = None
    git_in_container: bool = False
    rubric: list[dict[str, Any]] = field(default_factory=list)
    difficulty: float = 1.0

    def verification_spec(self) -> dict[str, Any] | None:
        if self.goal_kind != "engineering":
            return None
        spec: dict[str, Any] = {"fixture": self.fixture, "lab": self.lab}
        if self.workspace_mode != "local_fixture":
            spec["workspace_mode"] = self.workspace_mode
        if self.git_in_container:
            spec["git_in_container"] = True
        return spec

    def goal_payload_fields(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "brief": self.brief,
            "goal_kind": self.goal_kind,
            "project_id": self.project_id,
            "difficulty": self.difficulty,
        }
        if self.goal_kind == "engineering":
            payload["rubric"] = self.rubric or []
            payload["verification_spec"] = self.verification_spec()
            payload["min_reviewers"] = self.min_reviewers if self.min_reviewers is not None else 1
        else:
            payload["rubric"] = self.rubric or list(DEFAULT_CREATIVE_RUBRIC)
            payload["min_reviewers"] = self.min_reviewers if self.min_reviewers is not None else 3
            if self.pass_threshold is not None:
                payload["pass_threshold"] = self.pass_threshold
        if self.dispatch_isolated and self.dispatch_include_owners:
            payload["dispatch_include_owners"] = list(self.dispatch_include_owners)
        return payload


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in _BOOL_TRUE:
        return True
    if lowered in _BOOL_FALSE:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _parse_frontmatter_line(key: str, value: str, spec: dict[str, Any]) -> None:
    normalized = key.strip().lower()
    raw = value.strip()
    if normalized == "goal_kind":
        kind = raw.lower()
        if kind not in ("engineering", "creative"):
            raise ValueError("goal_kind must be engineering or creative")
        spec["goal_kind"] = kind
    elif normalized == "workspace_repo_url":
        spec["workspace_repo_url"] = raw
    elif normalized == "workspace_mode":
        mode = raw.lower()
        if mode not in ("local_fixture", "sandbox", "git", "windows"):
            raise ValueError("workspace_mode must be local_fixture, sandbox, git, or windows")
        spec["workspace_mode"] = mode
    elif normalized == "git_in_container":
        spec["git_in_container"] = _parse_bool(raw)
    elif normalized == "fixture":
        spec["fixture"] = raw
    elif normalized == "lab":
        spec["lab"] = raw
    elif normalized == "project_id":
        spec["project_id"] = raw
    elif normalized == "min_reviewers":
        spec["min_reviewers"] = int(raw)
    elif normalized == "pass_threshold":
        spec["pass_threshold"] = float(raw)
    elif normalized == "dispatch_isolated":
        spec["dispatch_isolated"] = _parse_bool(raw)
    elif normalized == "difficulty":
        spec["difficulty"] = float(raw)
    elif normalized == "dispatch_include_owners":
        spec["dispatch_include_owners"] = [
            part.strip() for part in raw.split(",") if part.strip()
        ]
    else:
        raise ValueError(f"unknown task file field: {key}")


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return {}, stripped.strip()

    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, stripped.strip()

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise ValueError("task file frontmatter missing closing ---")

    spec: dict[str, Any] = {}
    for line in lines[1:end_index]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        _parse_frontmatter_line(key, value, spec)

    body = "\n".join(lines[end_index + 1 :]).strip()
    return spec, body


def parse_task_text(text: str) -> TaskSpec:
    meta, brief = _split_frontmatter(text)
    if not brief:
        raise ValueError("task brief is empty")

    goal_kind = str(meta.get("goal_kind", DEFAULT_GOAL_KIND))
    fixture = str(meta.get("fixture", DEFAULT_FIXTURE))
    if goal_kind == "engineering" and fixture not in list_fixtures():
        known = ", ".join(list_fixtures())
        raise ValueError(f"unknown fixture {fixture!r}; expected one of: {known}")

    return TaskSpec(
        brief=brief,
        goal_kind=goal_kind,
        fixture=fixture,
        lab=str(meta.get("lab", "engineering-lab")),
        project_id=str(meta.get("project_id", DEFAULT_PROJECT_ID)),
        min_reviewers=meta.get("min_reviewers"),
        pass_threshold=meta.get("pass_threshold"),
        dispatch_isolated=bool(meta.get("dispatch_isolated", False)),
        dispatch_include_owners=meta.get("dispatch_include_owners"),
        workspace_mode=str(meta.get("workspace_mode", "local_fixture")),
        workspace_repo_url=meta.get("workspace_repo_url"),
        git_in_container=bool(meta.get("git_in_container", False)),
        difficulty=float(meta.get("difficulty", 1.0)),
    )


def load_task_file(path: str | Path) -> TaskSpec:
    task_path = Path(path)
    if not task_path.is_file():
        raise FileNotFoundError(f"task file not found: {task_path}")
    return parse_task_text(task_path.read_text(encoding="utf-8"))


def validate_task_spec(spec: TaskSpec) -> None:
    if not spec.brief.strip():
        raise ValueError("task brief is empty")
    if spec.goal_kind not in ("engineering", "creative"):
        raise ValueError("goal_kind must be engineering or creative")
    if spec.goal_kind == "engineering" and spec.fixture not in list_fixtures():
        known = ", ".join(list_fixtures())
        raise ValueError(f"unknown fixture {spec.fixture!r}; expected one of: {known}")
    if spec.git_in_container and spec.workspace_mode != "git":
        raise ValueError("git_in_container requires workspace_mode: git")
