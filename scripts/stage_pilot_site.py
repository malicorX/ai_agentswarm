#!/usr/bin/env python3
"""Stage the combined pilot static site (same layout as GitHub Pages)."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def stage_pilot_site(root: Path, output: Path) -> Path:
    pilot = root / "pilot"
    output.mkdir(parents=True, exist_ok=True)
    (output / "news-hub").mkdir(exist_ok=True)
    (output / "dashboard").mkdir(exist_ok=True)
    shutil.copy2(pilot / "index.html", output / "index.html")
    shutil.copytree(pilot / "news-hub", output / "news-hub", dirs_exist_ok=True)
    shutil.copytree(pilot / "dashboard", output / "dashboard", dirs_exist_ok=True)
    return output.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage AgentSwarm pilot static site")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory (default: <repo>/dist/pilot-site)",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    output = args.output or (root / "dist" / "pilot-site")
    if output.exists():
        shutil.rmtree(output)
    staged = stage_pilot_site(root, output)
    print(staged)


if __name__ == "__main__":
    main()
