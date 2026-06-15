#!/usr/bin/env python3
"""Verify Pages is live and record the URL in docs (P0.7 close-out)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_pages_ready.py"
RECORD_SCRIPT = REPO_ROOT / "scripts" / "record_pages_url.py"
DEFAULT_URL = "https://malicorx.github.io/ai_agentswarm"


def _load_check():
    spec = importlib.util.spec_from_file_location("check_pages_ready", CHECK_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    url = sys.argv[1].strip().rstrip("/") if len(sys.argv) > 1 else DEFAULT_URL
    check = _load_check()
    enabled, live_url = check.probe_pages()
    if not enabled:
        print("Pages is not enabled yet.", file=sys.stderr)
        check.print_admin_steps(check._repo_slug(None))
        print(
            "\nTrack progress: https://github.com/malicorX/ai_agentswarm/issues/1",
            file=sys.stderr,
        )
        return 1

    resolved = live_url or url
    if url and live_url and not (live_url == url or live_url.endswith(url)):
        print(f"Warning: expected {url}, API reports {live_url}", file=sys.stderr)

    record = subprocess.run(
        [sys.executable, str(RECORD_SCRIPT), resolved],
        check=False,
    )
    if record.returncode != 0:
        return record.returncode

    print(f"P0.7 close-out complete for {resolved}")
    print("Optional: run the 'Verify GitHub Pages' workflow in GitHub Actions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
