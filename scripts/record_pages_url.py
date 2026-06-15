#!/usr/bin/env python3
"""Record the live GitHub Pages URL in docs after P0.7 enablement."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/record_pages_url.py <https://...>", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1].strip().rstrip("/")
    if not url.startswith("https://"):
        print("URL must start with https://", file=sys.stderr)
        sys.exit(1)

    root = Path(__file__).resolve().parent.parent
    status_path = root / "docs" / "status.md"
    deploy_path = root / "docs" / "deploy.md"
    status_text = status_path.read_text(encoding="utf-8")
    deploy_text = deploy_path.read_text(encoding="utf-8")

    status_text = status_text.replace(
        "  - [ ] Enable GitHub Pages in repo settings (admin) + record live URL",
        f"  - [x] Enable GitHub Pages in repo settings (admin) + record live URL → {url}",
    )
    deploy_text = re.sub(
        r"\*\*Expected URL \(once enabled\):\*\* `[^`]+`",
        f"**Live URL:** `{url}/`",
        deploy_text,
        count=1,
    )

    status_path.write_text(status_text, encoding="utf-8")
    deploy_path.write_text(deploy_text, encoding="utf-8")
    print(f"Recorded live site URL: {url}")


if __name__ == "__main__":
    main()
