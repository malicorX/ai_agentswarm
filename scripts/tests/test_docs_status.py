"""Tests for the '## Since Phase 23' section in docs/status.md.

The section cites commit hashes in backticks. Each hash is checked with
'git cat-file -e <hash>^{commit}' in the repo root. These tests need the full
git history and the local tags; a shallow CI checkout without tags turns them
red. Without the section all tests fail (red before green).
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "docs" / "status.md"

HEADING = "## Since Phase 23"
THEMES = [
    "### Git-in-container sandbox",
    "### Task Console",
    "### Goal dispatch API",
    "### Pilot engineering-lab",
    "### Development process via Desk Lite",
]
HASH_RE = re.compile(r"`([0-9a-f]{7,40})`")


def _read():
    return STATUS.read_text(encoding="utf-8")


def _level(line):
    stripped = line.rstrip()
    match = re.match(r"^(#+) ", stripped)
    return len(match.group(1)) if match else 0


def _section(text, heading):
    """Text from heading up to the next heading of same or higher level, or EOF."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.rstrip() == heading]
    assert starts, f"heading missing in docs/status.md: {heading!r}"
    start = starts[0]
    level = _level(heading)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        other = _level(lines[i])
        if other and other <= level:
            end = i
            break
    return "\n".join(lines[start:end])


def _is_commit(sha):
    proc = subprocess.run(
        ["git", "cat-file", "-e", sha + "^{commit}"],
        cwd=ROOT,
        capture_output=True,
    )
    return proc.returncode == 0


def test_since_phase23_heading_once():
    lines = [line.rstrip() for line in _read().splitlines()]
    assert lines.count(HEADING) == 1, f"expected exactly one line {HEADING!r}"


def test_since_phase23_has_five_valid_hashes():
    section = _section(_read(), HEADING)
    hashes = sorted(set(HASH_RE.findall(section)))
    valid = [h for h in hashes if _is_commit(h)]
    invalid = [h for h in hashes if h not in valid]
    assert not invalid, f"hashes that are not commits: {invalid}"
    assert len(valid) >= 5, f"expected at least 5 distinct valid hashes, found {valid}"


def test_each_theme_has_valid_hash():
    section = _section(_read(), HEADING)
    for theme in THEMES:
        assert any(
            line.rstrip() == theme for line in section.splitlines()
        ), f"theme heading missing in '{HEADING}': {theme!r}"
        body = _section(section, theme)
        valid = [h for h in HASH_RE.findall(body) if _is_commit(h)]
        assert valid, f"no valid commit hash under {theme!r}"


KNOWN_GAPS = "### Known gaps"
TEST_DIRS = [
    "platform/tests",
    "agents/tests",
    "packages/mcp-adapter/tests",
    "pilot",
    "scripts/tests",
    "tools/tests",
]
# Assembled from parts so that this file does not match its own search.
EXPECTED_FAILURE_RE = "pytest\\.mark\\.x" + "fail|pytest\\.x" + "fail\\("


def test_known_gaps_lists_every_expected_failure():
    section = _section(_read(), KNOWN_GAPS)
    proc = subprocess.run(
        ["git", "grep", "-l", "-E", EXPECTED_FAILURE_RE, "--", *TEST_DIRS,
         ":(exclude)scripts/tests/test_docs_status.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    # git grep: 0 = matches, 1 = no match, anything else = error.
    assert proc.returncode in (0, 1), f"git grep failed ({proc.returncode}): {proc.stderr}"
    paths = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    missing = [p for p in paths if p not in section]
    assert not missing, f"expected-failure test files missing in {KNOWN_GAPS!r}: {missing}"


def test_known_gaps_names_debris_manifest_and_runners():
    section = _section(_read(), KNOWN_GAPS)
    for needle in [
        "REPO-DEBRIS-MANIFEST.md",
        "scripts/lite_full_suite.py",
        "scripts/run_all_tests.ps1",
        ".github/workflows/ci.yml",
    ]:
        assert needle in section, f"{needle!r} missing in {KNOWN_GAPS!r}"
