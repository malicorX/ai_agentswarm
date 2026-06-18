from __future__ import annotations

from pathlib import Path

import pytest

from agentswarm_agents.task_file import (
    TaskSpec,
    load_task_file,
    parse_task_text,
    validate_task_spec,
)


def test_parse_plain_text_defaults_to_engineering_primes() -> None:
    spec = parse_task_text("Create a Python script for primes.")
    assert spec.brief == "Create a Python script for primes."
    assert spec.goal_kind == "engineering"
    assert spec.fixture == "primes"
    assert spec.verification_spec() == {"fixture": "primes", "lab": "engineering-lab"}


def test_parse_frontmatter_engineering() -> None:
    text = """---
goal_kind: engineering
fixture: fizzbuzz
project_id: lab
---
Implement fizzbuzz for 1..100.
"""
    spec = parse_task_text(text)
    assert spec.goal_kind == "engineering"
    assert spec.fixture == "fizzbuzz"
    assert spec.project_id == "lab"
    assert spec.brief == "Implement fizzbuzz for 1..100."


def test_parse_frontmatter_creative() -> None:
    text = """---
goal_kind: creative
min_reviewers: 2
---
Write a haiku about distributed systems.
"""
    spec = parse_task_text(text)
    assert spec.goal_kind == "creative"
    assert spec.min_reviewers == 2
    payload = spec.goal_payload_fields()
    assert payload["goal_kind"] == "creative"
    assert payload["min_reviewers"] == 2
    assert payload["rubric"]


def test_parse_rejects_unknown_fixture() -> None:
    with pytest.raises(ValueError, match="unknown fixture"):
        parse_task_text("---\nfixture: unknown\n---\nDo work.")


def test_parse_rejects_empty_brief() -> None:
    with pytest.raises(ValueError, match="brief is empty"):
        parse_task_text("---\ngoal_kind: engineering\n---\n   \n")


def test_load_task_file_example(tmp_path: Path) -> None:
    task_path = tmp_path / "task.txt"
    task_path.write_text(
        "---\ngoal_kind: engineering\nfixture: primes\n---\nPrint primes.\n",
        encoding="utf-8",
    )
    spec = load_task_file(task_path)
    assert isinstance(spec, TaskSpec)
    assert spec.brief == "Print primes."


def test_dispatch_isolated_flag() -> None:
    spec = TaskSpec(
        brief="work",
        dispatch_isolated=True,
        dispatch_include_owners=["solve-coordinator-abc"],
    )
    payload = spec.goal_payload_fields()
    assert payload["dispatch_include_owners"] == ["solve-coordinator-abc"]


def test_validate_task_spec_ok() -> None:
    validate_task_spec(parse_task_text("Do something useful."))


def test_validate_task_spec_rejects_empty_brief() -> None:
    with pytest.raises(ValueError, match="brief is empty"):
        validate_task_spec(TaskSpec(brief="   "))
