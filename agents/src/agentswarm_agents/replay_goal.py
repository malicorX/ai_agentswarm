"""Operator replay: browse goal workspace and re-run verification in a sandbox."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from agentswarm_agents.client_data_dir import client_data_dir
from agentswarm_agents.engineering_lab import fixture_dir
from agentswarm_agents.engineering_workspace import (
    clone_at_workspace_ref,
    resolve_engineering_git_workspace,
    run_pytest_in_dir,
    workspace_mode,
)
from agentswarm_agents.sandbox_executor import docker_available, run_fixture_tests_sandbox

SKIP_TREE_NAMES = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv"}
MAX_TREE_ENTRIES = 500
MAX_FILE_BYTES = 512_000


def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    token = os.environ.get("AGENTSWARM_BOOTSTRAP_TOKEN") or os.environ.get(
        "AGENTSWARM_OWNER_TOKEN"
    )
    if token:
        headers["X-Bootstrap-Token"] = token
    return headers


def fetch_replay_context(base_url: str, goal_id: str) -> dict[str, Any]:
    """Load goal fields needed for operator replay (includes forge creds when authorized)."""
    clean = base_url.rstrip("/")
    headers = _auth_headers()
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(
            f"{clean}/creative/goals/{goal_id}/replay-context",
            headers=headers,
        )
        if response.status_code == 404:
            detail = ""
            try:
                detail = str(response.json().get("detail", ""))
            except json.JSONDecodeError:
                pass
            if "not found" in detail.lower() and "goal" in detail.lower():
                raise ValueError(f"goal not found: {goal_id}")
            return _fetch_replay_context_legacy(client, clean, goal_id, headers)
        if response.status_code == 401:
            raise PermissionError(
                "replay-context requires AGENTSWARM_BOOTSTRAP_TOKEN in the task console environment"
            )
        response.raise_for_status()
        return response.json()


def _fetch_replay_context_legacy(
    client: httpx.Client,
    clean: str,
    goal_id: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Older platforms lack /replay-context; assemble from public goal + trace."""
    goal_response = client.get(f"{clean}/creative/goals/{goal_id}")
    if goal_response.status_code == 404:
        raise ValueError(f"goal not found: {goal_id}")
    goal_response.raise_for_status()
    goal = goal_response.json()
    return {
        "goal_id": goal_id,
        "goal_kind": str(goal.get("goal_kind", "creative")),
        "status": str(goal.get("status", "")),
        "brief": str(goal.get("brief", "")),
        "artifact_text": goal.get("artifact_text"),
        "workspace_ref": goal.get("workspace_ref"),
        "verification_spec": goal.get("verification_spec"),
        "workspace": goal.get("workspace"),
        "forge_credentials": None,
    }


def _verification_spec(ctx: dict[str, Any]) -> dict[str, Any]:
    spec = ctx.get("verification_spec")
    return dict(spec) if isinstance(spec, dict) else {}


def _workspace_ref(ctx: dict[str, Any]) -> str | None:
    ref = ctx.get("workspace_ref")
    if isinstance(ref, str) and ref.strip():
        return ref.strip()
    for step in ctx.get("trace_steps") or []:
        step_ref = step.get("workspace_ref")
        if isinstance(step_ref, str) and step_ref.strip():
            return step_ref.strip()
        result = step.get("result")
        if isinstance(result, dict):
            nested = result.get("workspace_ref") or (result.get("git_artifact") or {}).get(
                "commit_sha"
            )
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _git_info(ctx: dict[str, Any]) -> dict[str, str]:
    workspace = ctx.get("workspace")
    if isinstance(workspace, dict) and workspace.get("repo_url"):
        return {
            "repo_url": str(workspace["repo_url"]),
            "default_branch": str(workspace.get("default_branch", "main")),
            "forge_type": str(workspace.get("forge_type", "git")),
        }
    spec = _verification_spec(ctx)
    env_url = os.environ.get("AGENTSWARM_GIT_REPO_URL", "").strip()
    repo_url = str(spec.get("workspace_repo_url") or env_url or "").strip()
    if not repo_url:
        fixture = str(spec.get("fixture", "primes"))
        resolved = resolve_engineering_git_workspace(fixture=fixture)
        return {
            "repo_url": resolved["repo_url"],
            "default_branch": resolved.get("default_branch", "main"),
            "forge_type": resolved.get("forge_type", "git"),
        }
    return {
        "repo_url": repo_url,
        "default_branch": "main",
        "forge_type": "git",
    }


def _forge_credentials(ctx: dict[str, Any]) -> dict[str, Any] | None:
    forge = ctx.get("forge_credentials")
    return dict(forge) if isinstance(forge, dict) else None


def _replay_cache_dir(goal_id: str, workspace_ref: str) -> Path:
    safe_ref = workspace_ref.replace("/", "_")[:16]
    path = client_data_dir() / "replay-cache" / goal_id / safe_ref
    path.mkdir(parents=True, exist_ok=True)
    return path


def _checkout_workspace(ctx: dict[str, Any]) -> tuple[Path, str]:
    mode = workspace_mode(_verification_spec(ctx))
    goal_kind = str(ctx.get("goal_kind", "engineering"))
    if goal_kind != "engineering":
        raise ValueError("workspace checkout is only available for engineering goals")

    workspace_ref = _workspace_ref(ctx)
    if mode == "git":
        if not workspace_ref:
            raise ValueError("goal has no workspace_ref yet — wait for codewriter to submit")
        git_info = _git_info(ctx)
        cache = _replay_cache_dir(str(ctx["goal_id"]), workspace_ref)
        marker = cache / ".agentswarm-ref"
        dest = cache / "tree"
        if (
            marker.is_file()
            and marker.read_text(encoding="utf-8").strip() == workspace_ref
            and dest.is_dir()
        ):
            return dest, workspace_ref
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
        cache.mkdir(parents=True, exist_ok=True)
        workdir = clone_at_workspace_ref(
            git_info["repo_url"],
            workspace_ref,
            default_branch=git_info.get("default_branch", "main"),
            forge_credentials=_forge_credentials(ctx),
        )
        dest = cache / "tree"
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(workdir), str(dest))
        marker.write_text(workspace_ref, encoding="utf-8")
        return dest, workspace_ref

    fixture = str(_verification_spec(ctx).get("fixture", "primes"))
    from agentswarm_agents.engineering_lab import fixture_dir

    host_fixture = fixture_dir(fixture)
    if not host_fixture.is_dir():
        raise FileNotFoundError(f"engineering fixture not found: {fixture}")
    warning = (
        "Replay uses the local engineering-lab fixture on this machine. "
        "For distributed goals, use workspace_mode: git so workspace_ref is authoritative."
    )
    return host_fixture, warning


def list_workspace_tree(ctx: dict[str, Any], *, prefix: str = "") -> dict[str, Any]:
    goal_kind = str(ctx.get("goal_kind", "engineering"))
    if goal_kind == "creative":
        text = ctx.get("artifact_text")
        return {
            "mode": "creative",
            "workspace_ref": ctx.get("workspace_ref"),
            "artifact_text": text,
            "entries": [],
        }

    root, ref_or_note = _checkout_workspace(ctx)
    mode = workspace_mode(_verification_spec(ctx))
    entries: list[dict[str, Any]] = []
    count = 0
    prefix_path = Path(prefix) if prefix else Path(".")
    scan_root = (root / prefix_path).resolve()
    if not str(scan_root).startswith(str(root.resolve())):
        raise ValueError("invalid path")
    if not scan_root.is_dir():
        raise FileNotFoundError(f"not a directory: {prefix or '/'}")

    for path in sorted(scan_root.rglob("*")):
        if count >= MAX_TREE_ENTRIES:
            break
        rel = path.relative_to(root)
        if any(part in SKIP_TREE_NAMES for part in rel.parts):
            continue
        if path.is_dir():
            kind = "dir"
        else:
            kind = "file"
        entries.append(
            {
                "path": rel.as_posix(),
                "kind": kind,
                "size": path.stat().st_size if path.is_file() else None,
            }
        )
        count += 1

    payload: dict[str, Any] = {
        "mode": mode,
        "workspace_ref": ref_or_note if mode == "git" else _workspace_ref(ctx),
        "root": str(root),
        "entries": entries,
        "truncated": count >= MAX_TREE_ENTRIES,
    }
    if mode != "git" and isinstance(ref_or_note, str) and ref_or_note.startswith("Replay"):
        payload["warning"] = ref_or_note
    return payload


def read_workspace_file(ctx: dict[str, Any], *, path: str) -> dict[str, Any]:
    if not path or path.startswith("/") or ".." in Path(path).parts:
        raise ValueError("invalid file path")
    root, _ = _checkout_workspace(ctx)
    target = (root / path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise ValueError("invalid file path")
    if not target.is_file():
        raise FileNotFoundError(f"file not found: {path}")
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"file too large for preview ({size} bytes; max {MAX_FILE_BYTES})")
    text = target.read_text(encoding="utf-8", errors="replace")
    return {"path": path, "size": size, "content": text}


def verify_goal_locally(ctx: dict[str, Any]) -> dict[str, Any]:
    goal_kind = str(ctx.get("goal_kind", "engineering"))
    goal_id = str(ctx.get("goal_id", ""))
    status = str(ctx.get("status", ""))
    spec = dict(_verification_spec(ctx))
    spec.setdefault("sandbox_run_id", f"replay-{goal_id}")

    if goal_kind == "creative":
        return {
            "mode": "creative",
            "passed": status == "verified",
            "goal_status": status,
            "artifact_text": ctx.get("artifact_text"),
            "message": "Creative goals expose artifact_text; no sandbox run required.",
        }

    mode = workspace_mode(spec)
    workspace_ref = _workspace_ref(ctx)

    if mode == "git":
        if not workspace_ref:
            raise ValueError("goal has no workspace_ref yet — cannot verify")
        root, _ref_or_note = _checkout_workspace(ctx)
        result = run_pytest_in_dir(root)
        result["replay_mode"] = "git_host_cache"
        result["workspace_ref"] = workspace_ref
        result["goal_status"] = status
        return result

    if mode in ("sandbox", "local_fixture"):
        warning = None
        if mode == "local_fixture":
            warning = (
                "local_fixture replay runs pytest on this machine's engineering-lab checkout. "
                "Remote worker patches are not visible unless you use workspace_mode: git."
            )
        if not docker_available():
            raise RuntimeError(
                "Docker is required to verify engineering goals safely on the operator machine"
            )
        result = run_fixture_tests_sandbox(spec)
        result["replay_mode"] = f"{mode}_sandbox"
        result["goal_status"] = status
        if warning:
            result["warning"] = warning
        return result

    raise ValueError(f"unsupported workspace_mode for replay: {mode}")


def build_workspace_zip(ctx: dict[str, Any]) -> tuple[bytes, str]:
    """Zip the replay workspace for download (engineering checkout or creative artifact)."""
    goal_id = str(ctx.get("goal_id", "goal"))
    goal_kind = str(ctx.get("goal_kind", "engineering"))
    if goal_kind == "creative":
        text = str(ctx.get("artifact_text") or "")
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("artifact.txt", text)
        return buffer.getvalue(), f"{goal_id}-artifact.zip"

    root, ref_or_note = _checkout_workspace(ctx)
    workspace_ref = _workspace_ref(ctx)
    ref_label = workspace_ref[:12] if isinstance(workspace_ref, str) and workspace_ref else "workspace"
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in SKIP_TREE_NAMES for part in rel.parts):
                continue
            archive.write(path, arcname=rel.as_posix())
    if isinstance(ref_or_note, str) and not ref_or_note.startswith("Replay"):
        ref_label = ref_or_note[:12]
    return buffer.getvalue(), f"{goal_id}-{ref_label}.zip"


def merge_trace_into_context(
    ctx: dict[str, Any], trace: dict[str, Any] | None
) -> dict[str, Any]:
    merged = dict(ctx)
    if trace:
        merged["trace_steps"] = trace.get("steps") or []
        if not merged.get("workspace_ref") and trace.get("workspace_ref"):
            merged["workspace_ref"] = trace["workspace_ref"]
        if not merged.get("artifact_text") and trace.get("artifact_text"):
            merged["artifact_text"] = trace["artifact_text"]
    return merged


def main() -> None:
    import argparse
    import sys

    from agentswarm_agents.client import platform_url

    parser = argparse.ArgumentParser(
        prog="agentswarm-replay-goal",
        description="Browse or re-verify a goal workspace on the operator machine",
    )
    parser.add_argument("goal_id", help="goal id to replay")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENTSWARM_STAGING_API_URL", platform_url()),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tree", help="List workspace files")
    read_p = sub.add_parser("read", help="Print one workspace file")
    read_p.add_argument("path", help="relative path inside workspace")
    sub.add_parser("verify", help="Re-run verification in sandbox")
    args = parser.parse_args()
    try:
        ctx = fetch_replay_context(args.base_url.rstrip("/"), args.goal_id)
    except (ValueError, PermissionError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.command == "tree":
        print(json.dumps(list_workspace_tree(ctx), indent=2))
    elif args.command == "read":
        print(read_workspace_file(ctx, path=args.path)["content"])
    elif args.command == "verify":
        print(json.dumps(verify_goal_locally(ctx), indent=2))


if __name__ == "__main__":
    main()
