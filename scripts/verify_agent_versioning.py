#!/usr/bin/env python3
"""Verify agent versioning registry behavior (P5.7)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TESTS = [
    _ROOT / "platform" / "tests" / "test_agent_versioning.py",
    _ROOT / "platform" / "tests" / "test_version_probation.py",
]


def main() -> int:
    missing = [path for path in _TESTS if not path.is_file()]
    if missing:
        for path in missing:
            print(f"Missing {path}", file=sys.stderr)
        return 1
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *[str(path) for path in _TESTS], "-q"],
        cwd=_ROOT,
        check=False,
    )
    if proc.returncode != 0:
        print("Agent versioning verify failed", file=sys.stderr)
        return proc.returncode
    print("Agent versioning OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
