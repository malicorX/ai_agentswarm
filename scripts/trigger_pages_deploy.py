#!/usr/bin/env python3
"""Dispatch the GitHub Actions workflow that deploys the pilot site to Pages."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


def workflow_dispatch_via_api(
    *,
    repo: str,
    workflow_file: str,
    ref: str,
    token: str,
    artifact_ref: str | None,
) -> None:
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/dispatches"
    body: dict[str, object] = {"ref": ref}
    if artifact_ref:
        body["inputs"] = {"artifact_ref": artifact_ref}
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status not in (200, 204):
                raise RuntimeError(f"unexpected status {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"workflow dispatch failed ({exc.code}): {detail}") from exc


def workflow_dispatch_via_gh(
    *,
    repo: str,
    workflow_name: str,
    ref: str,
    artifact_ref: str | None,
) -> None:
    cmd = [
        "gh",
        "workflow",
        "run",
        workflow_name,
        "--repo",
        repo,
        "--ref",
        ref,
    ]
    if artifact_ref:
        cmd.extend(["-f", f"artifact_ref={artifact_ref}"])
    subprocess.run(cmd, check=True, timeout=60)


def main() -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "malicorX/ai_agentswarm").strip()
    workflow_file = os.environ.get("AGENTSWARM_PAGES_WORKFLOW", "pages.yml").strip()
    workflow_name = os.environ.get(
        "AGENTSWARM_PAGES_WORKFLOW_NAME", "Deploy pilot site"
    ).strip()
    ref = os.environ.get("AGENTSWARM_PAGES_DEPLOY_REF", "main").strip()
    artifact_ref = (
        os.environ.get("AGENTSWARM_DEPLOY_ARTIFACT_REF", "").strip() or None
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    if shutil.which("gh") and not token:
        workflow_dispatch_via_gh(
            repo=repo,
            workflow_name=workflow_name,
            ref=ref,
            artifact_ref=artifact_ref,
        )
        print(f"dispatched {workflow_name} on {repo}@{ref}")
        return

    if not token:
        print(
            "Set GITHUB_TOKEN (repo workflow scope) or authenticate `gh` CLI",
            file=sys.stderr,
        )
        sys.exit(1)

    workflow_dispatch_via_api(
        repo=repo,
        workflow_file=workflow_file,
        ref=ref,
        token=token.strip(),
        artifact_ref=artifact_ref,
    )
    print(f"dispatched {workflow_file} on {repo}@{ref}")


if __name__ == "__main__":
    main()
