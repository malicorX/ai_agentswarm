#!/usr/bin/env python3
"""Record the live pilot static site URL in docs (theebie.de, GitHub Pages, etc.)."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def record_pilot_url(root: Path, url: str, *, recorded_at: str | None = None) -> None:
    clean = url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("URL must start with https://")

    recorded = recorded_at or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    host = (urlparse(clean).hostname or "").lower()
    on_theebie = host.endswith("theebie.de")

    status_path = root / "docs" / "status.md"
    deploy_path = root / "docs" / "deploy.md"
    readme_path = root / "README.md"
    status_text = status_path.read_text(encoding="utf-8")
    deploy_text = deploy_path.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8")

    status_text = status_text.replace(
        "- [ ] Manual deploy by human maintainer",
        "- [x] Manual deploy by human maintainer",
        1,
    )
    if on_theebie:
        status_text = status_text.replace(
            "  - [ ] Host pilot static site on theebie.de (`/sites/agentswarm/`) + record live URL",
            f"  - [x] Host pilot static site on theebie.de (`/sites/agentswarm/`) + record live URL → {clean}",
        )
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
    deploy_text = re.sub(
        r"\*\*Maintainer URL \(theebie\.de\):\*\* `[^`]+`",
        f"**Maintainer URL (theebie.de):** `{clean}/`",
        deploy_text,
        count=1,
    )
    deploy_text = deploy_text.replace(
        "- [ ] Pilot static site hosted (URL recorded below)",
        "- [x] Pilot static site hosted (URL recorded below)",
        1,
    )
    deploy_text = re.sub(
        r"\| AI News Hub pilot \| [^|]+ \|[^|]*\|",
        f"| AI News Hub pilot | {clean}/news-hub/ | {recorded} |",
        deploy_text,
        count=1,
    )

    readme_text = re.sub(
        r"\| \*\*Public pilot\*\* \| \*\*Pending\*\*[^|]+\|",
        f"| **Public pilot** | [{clean}/]({clean}/) · [dashboard]({clean}/dashboard/) |",
        readme_text,
        count=1,
    )

    status_path.write_text(status_text, encoding="utf-8")
    deploy_path.write_text(deploy_text, encoding="utf-8")
    readme_path.write_text(readme_text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/record_pilot_url.py <https://...>", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent.parent
    try:
        record_pilot_url(root, sys.argv[1])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Recorded live site URL: {sys.argv[1].strip().rstrip('/')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
