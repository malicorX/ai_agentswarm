from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parent.parent
HELLO_PY = FIXTURE_ROOT / "hello.py"
HELLO_EXE = FIXTURE_ROOT / "hello.exe"


def test_greet_function() -> None:
    sys.path.insert(0, str(FIXTURE_ROOT))
    try:
        import hello as hello_mod
    finally:
        sys.path.pop(0)
    assert hello_mod.greet("agentswarm") == "hello agentswarm"


def test_native_exe_outputs_greeting() -> None:
    if not HELLO_EXE.is_file():
        import pytest

        pytest.skip("hello.exe not built yet (run builder.compile in Windows VM)")
    proc = subprocess.run(
        [str(HELLO_EXE)],
        cwd=FIXTURE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert proc.stdout.strip() == "hello agentswarm"
