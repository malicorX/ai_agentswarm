#!/usr/bin/env python3
"""Backward-compatible alias for record_pilot_url (GitHub Pages naming)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_RECORD_PILOT = Path(__file__).resolve().parent / "record_pilot_url.py"


def _load_record_pilot():
    spec = importlib.util.spec_from_file_location("record_pilot_url", _RECORD_PILOT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record_pages_url(root: Path, url: str, *, recorded_at: str | None = None) -> None:
    _load_record_pilot().record_pilot_url(root, url, recorded_at=recorded_at)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/record_pages_url.py <https://...>", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent.parent
    try:
        record_pages_url(root, sys.argv[1])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Recorded live site URL: {sys.argv[1].strip().rstrip('/')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
