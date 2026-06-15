#!/usr/bin/env python3
"""Verify agent versioning registry behavior (P5.7)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TESTS = _ROOT / "platform" / "tests" / "test_agent_versioning.py"


def main() -> int:
    if not _TESTS.is_file():
        print(f"Missing {_TESTS}", file=sys.stderr)
        return 1
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(_TESTS), "-q"],
        cwd=_ROOT / "platform",
        check=False,
    )
    if proc.returncode != 0:
        print("Agent versioning verify failed", file=sys.stderr)
        return proc.returncode
    print("Agent versioning OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
