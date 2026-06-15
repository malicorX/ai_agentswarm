#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

from capsule_executor import execute_capsule


def main() -> int:
    try:
        assignment = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid stdin JSON: {exc}"}), file=sys.stderr)
        return 1
    if not isinstance(assignment, dict):
        print(json.dumps({"error": "assignment must be a JSON object"}), file=sys.stderr)
        return 1
    result = execute_capsule(assignment)
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
