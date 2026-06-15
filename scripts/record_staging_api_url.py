#!/usr/bin/env python3
"""Record the live staging platform API URL in docs."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def record_staging_api_url(root: Path, url: str, *, recorded_at: str | None = None) -> None:
    clean = url.strip().rstrip("/")
    if not clean.startswith("https://"):
        raise ValueError("URL must start with https://")

    recorded = recorded_at or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status_path = root / "docs" / "status.md"
    deploy_path = root / "docs" / "deploy.md"
    readme_path = root / "README.md"
    execution_path = root / "docs" / "execution-plan.md"

    status_text = status_path.read_text(encoding="utf-8")
    deploy_text = deploy_path.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8")
    execution_text = execution_path.read_text(encoding="utf-8")

    if "| **P6.10** |" in status_text:
        status_text = re.sub(
            r"\| \*\*P6\.10\*\* \| [^|]+ \| [^|]+ \|",
            f"| **P6.10** | Staging API on theebie.de (`/agentswarm/api`) | Done → {clean} |",
            status_text,
            count=1,
        )
    else:
        status_text = status_text.replace(
            "| **P6.9** | Git-backed coder capsule | Done |",
            f"| **P6.9** | Git-backed coder capsule | Done |\n"
            f"| **P6.10** | Staging API on theebie.de (`/agentswarm/api`) | Done → {clean} |",
            1,
        )

    status_text = status_text.replace(
        "  - [ ] Optional: platform on VPS with HTTPS",
        f"  - [x] Optional: platform on VPS with HTTPS → staging {clean}",
        1,
    )

    deploy_text = deploy_text.replace(
        "- [ ] Platform runs on VPS with systemd",
        "- [x] Platform runs on VPS with systemd (theebie staging)",
        1,
    )
    deploy_text = deploy_text.replace(
        "- [ ] HTTPS via reverse proxy",
        "- [x] HTTPS via reverse proxy (Caddy on theebie.de)",
        1,
    )
    deploy_text = deploy_text.replace(
        '- [ ] `GET /health` returns `{"status":"ok"}` on public URL',
        '- [x] `GET /health` returns `{"status":"ok"}` on public URL',
        1,
    )
    deploy_text = re.sub(
        r"\| Platform API \| [^|]+ \|[^|]*\|",
        f"| Platform API (staging) | {clean} | {recorded} |",
        deploy_text,
        count=1,
    )

    execution_text = execution_text.replace(
        "→  P6.10 Staging API on theebie.de",
        f"✅ P6.10 Staging API on theebie.de → {clean}",
        1,
    )

    if "| **Staging API** |" not in readme_text:
        readme_text = readme_text.replace(
            "| **Public pilot** |",
            f"| **Staging API** | [{clean}]({clean}/health) |\n| **Public pilot** |",
            1,
        )

    status_path.write_text(status_text, encoding="utf-8")
    deploy_path.write_text(deploy_text, encoding="utf-8")
    readme_path.write_text(readme_text, encoding="utf-8")
    execution_path.write_text(execution_text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/record_staging_api_url.py <https://...>", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent.parent
    try:
        record_staging_api_url(root, sys.argv[1])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Recorded staging API URL: {sys.argv[1].strip().rstrip('/')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
