"""Worker container stdin/stdout protocol for docker runtime assignments."""

from __future__ import annotations

import json
import sys
from typing import Any

from agentswarm_agents.capsule_executor import execute_capsule
from agentswarm_agents.worker_llm import execute_capsule_with_local_llm, model_path_from_env


def run_worker_assignment(assignment: dict[str, Any]) -> dict[str, Any]:
    if model_path_from_env() is not None:
        return execute_capsule_with_local_llm(assignment)
    return execute_capsule(assignment)


def main() -> int:
    try:
        assignment = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid stdin JSON: {exc}"}), file=sys.stderr)
        return 1
    if not isinstance(assignment, dict):
        print(json.dumps({"error": "assignment must be a JSON object"}), file=sys.stderr)
        return 1
    try:
        result = run_worker_assignment(assignment)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
