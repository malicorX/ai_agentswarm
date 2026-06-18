from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parent.parent
FIZZBUZZ_PY = FIXTURE_ROOT / "fizzbuzz.py"


def _line(value: int) -> str:
    if value % 15 == 0:
        return "FizzBuzz"
    if value % 3 == 0:
        return "Fizz"
    if value % 5 == 0:
        return "Buzz"
    return str(value)


def test_fizzbuzz_script_outputs_1_to_100() -> None:
    proc = subprocess.run(
        [sys.executable, str(FIZZBUZZ_PY)],
        cwd=FIXTURE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    lines = [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
    expected = [_line(i) for i in range(1, 101)]
    assert lines == expected
