#!/usr/bin/env python3
"""Record the live GitHub Pages URL in docs after P0.7 enablement."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def record_pages_url(root: Path, url: str) -> None:
    clean = url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("URL must start with https://")

    status_path = root / "docs" / "status.md"
    deploy_path = root / "docs" / "deploy.md"
    status_text = status_path.read_text(encoding="utf-8")
    deploy_text = deploy_path.read_text(encoding="utf-8")

    status_text = status_text.replace(
        "  - [ ] Enable GitHub Pages in repo settings (admin) + record live URL",
        f"  - [x] Enable GitHub Pages in repo settings (admin) + record live URL → {clean}",
    )
    deploy_text = re.sub(
        r"\*\*Expected URL \(once enabled\):\*\* `[^`]+`",
        f"**Live URL:** `{clean}/`",
        deploy_text,
        count=1,
    )

    status_path.write_text(status_text, encoding="utf-8")
    deploy_path.write_text(deploy_text, encoding="utf-8")


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
