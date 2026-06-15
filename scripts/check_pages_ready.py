#!/usr/bin/env python3
"""Verify GitHub Pages is enabled for the repo (exit 0) or print admin steps (exit 1)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def _repo_slug(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    env = os.environ.get("AGENTSWARM_GITHUB_REPO", "").strip()
    if env:
        return env
    return "malicorX/ai_agentswarm"


def _fetch_pages_api(repo: str, token: str | None) -> tuple[int, dict | None]:
    url = f"https://api.github.com/repos/{repo}/pages"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agentswarm-check-pages",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = None
        try:
            body = json.loads(exc.read().decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = None
        return exc.code, body


def _fetch_via_gh(repo: str) -> tuple[int, dict | None]:
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{repo}/pages"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return 0, None
    if proc.returncode != 0:
        return 404, None
    try:
        return 200, json.loads(proc.stdout)
    except json.JSONDecodeError:
        return 200, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        help="GitHub owner/repo (default: AGENTSWARM_GITHUB_REPO or malicorX/ai_agentswarm)",
    )
    parser.add_argument(
        "--expected-url",
        help="Fail unless Pages html_url matches (suffix match allowed)",
    )
    args = parser.parse_args()

    repo = _repo_slug(args.repo)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    status, body = _fetch_pages_api(repo, token)
    if status == 404 and not token:
        gh_status, gh_body = _fetch_via_gh(repo)
        if gh_status == 200:
            status, body = gh_status, gh_body

    if status == 404:
        print(f"GitHub Pages is not enabled for {repo}.", file=sys.stderr)
        print(file=sys.stderr)
        print("Admin steps:", file=sys.stderr)
        print(f"  1. Open https://github.com/{repo}/settings/pages", file=sys.stderr)
        print("  2. Build and deployment → Source: GitHub Actions", file=sys.stderr)
        print(
            f"  3. Re-run https://github.com/{repo}/actions/workflows/pages.yml",
            file=sys.stderr,
        )
        print(
            "  4. After deploy: python scripts/record_pages_url.py <live-url>",
            file=sys.stderr,
        )
        return 1

    if status != 200 or not body:
        print(f"Unexpected GitHub API response ({status}) for {repo}.", file=sys.stderr)
        return 2

    html_url = str(body.get("html_url") or "").rstrip("/")
    print(f"Pages enabled: {html_url or '(url pending)'}")

    if args.expected_url:
        expected = args.expected_url.rstrip("/")
        if html_url and not (html_url == expected or html_url.endswith(expected)):
            print(f"Expected URL {expected}, got {html_url}", file=sys.stderr)
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
