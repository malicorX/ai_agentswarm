from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentswarm_agents.client import repo_root

IMPLEMENT_MARKER = "<!-- agentswarm:implement -->"


@dataclass(frozen=True)
class FixtureSpec:
    name: str
    patch_file: str
    stub: str
    mock_body: str


_MOCK_PRIMES_BODY = """\
def first_n_primes(count: int) -> list[int]:
    primes: list[int] = []
    candidate = 2
    while len(primes) < count:
        if all(candidate % p != 0 for p in primes):
            primes.append(candidate)
        candidate += 1
    return primes


def main() -> None:
    for value in first_n_primes(100):
        print(value)


if __name__ == "__main__":
    main()
"""

_MOCK_FIZZBUZZ_BODY = """\
def fizzbuzz_line(value: int) -> str:
    if value % 15 == 0:
        return "FizzBuzz"
    if value % 3 == 0:
        return "Fizz"
    if value % 5 == 0:
        return "Buzz"
    return str(value)


def main() -> None:
    for value in range(1, 101):
        print(fizzbuzz_line(value))


if __name__ == "__main__":
    main()
"""

_MOCK_WINHELLO_BODY = """\
def greet(name: str) -> str:
    return f"hello {name}"


def main() -> None:
    print(greet("agentswarm"))


if __name__ == "__main__":
    main()
"""

FIXTURES: dict[str, FixtureSpec] = {
    "primes": FixtureSpec(
        name="primes",
        patch_file="primes.py",
        stub=(
            '"""Engineering-lab fixture: first 100 primes (implement below marker)."""\n\n'
            f"# {IMPLEMENT_MARKER}\n"
        ),
        mock_body=_MOCK_PRIMES_BODY,
    ),
    "fizzbuzz": FixtureSpec(
        name="fizzbuzz",
        patch_file="fizzbuzz.py",
        stub=(
            '"""Engineering-lab fixture: FizzBuzz 1..100 (implement below marker)."""\n\n'
            f"# {IMPLEMENT_MARKER}\n"
        ),
        mock_body=_MOCK_FIZZBUZZ_BODY,
    ),
    "winhello": FixtureSpec(
        name="winhello",
        patch_file="hello.py",
        stub=(
            '"""Windows VM fixture: build hello.exe and run natively (implement below marker)."""\n\n'
            f"# {IMPLEMENT_MARKER}\n"
        ),
        mock_body=_MOCK_WINHELLO_BODY,
    ),
}


def list_fixtures() -> list[str]:
    return sorted(FIXTURES.keys())


def get_fixture_spec(fixture: str) -> FixtureSpec:
    spec = FIXTURES.get(fixture)
    if spec is None:
        raise ValueError(f"unknown engineering fixture: {fixture!r}")
    return spec


def engineering_lab_root() -> Path:
    return Path(repo_root()) / "pilot" / "engineering-lab"


def fixture_dir(fixture: str) -> Path:
    return engineering_lab_root() / fixture


def default_verification_spec(fixture: str = "primes") -> dict[str, str]:
    get_fixture_spec(fixture)
    return {"fixture": fixture, "lab": "engineering-lab"}


def reset_fixture(fixture: str) -> None:
    """Restore the engineering-lab fixture stub (for repeatable demos)."""
    spec = get_fixture_spec(fixture)
    target = fixture_dir(fixture) / spec.patch_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(spec.stub, encoding="utf-8")


def mock_body_for_fixture(fixture: str) -> str:
    return get_fixture_spec(fixture).mock_body


def apply_engineering_patch(capsule: dict[str, Any]) -> dict[str, Any]:
    lab = capsule.get("lab")
    patch = capsule.get("patch")
    if not isinstance(lab, dict):
        raise ValueError("engineering codewriter capsule requires lab section")
    if not isinstance(patch, dict):
        raise ValueError("engineering codewriter capsule requires patch section")
    fixture = str(lab.get("fixture", "primes"))
    spec = get_fixture_spec(fixture)
    rel_file = str(patch.get("file", spec.patch_file))
    marker = str(patch.get("marker", IMPLEMENT_MARKER))
    insert = patch.get("insert")
    if insert is None:
        insert = spec.mock_body
    target = fixture_dir(fixture) / rel_file
    if not target.exists():
        raise FileNotFoundError(f"engineering fixture file not found: {target}")
    content = target.read_text(encoding="utf-8")
    if marker in content:
        new_content = content.replace(marker, f"{marker}\n{insert}")
    else:
        new_content = content + f"\n{marker}\n{insert}\n"
    target.write_text(new_content, encoding="utf-8")
    return {
        "applied": True,
        "fixture": fixture,
        "file": rel_file,
        "bytes_written": len(new_content),
    }


def run_fixture_tests(verification_spec: dict[str, Any]) -> dict[str, Any]:
    fixture = str(verification_spec.get("fixture", "primes"))
    root = fixture_dir(fixture)
    if not root.is_dir():
        raise FileNotFoundError(f"engineering fixture not found: {fixture}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "fixture": fixture,
    }
