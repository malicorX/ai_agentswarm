"""Content-addressed artifact blob storage (D2)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

_DIGEST_RE = re.compile(r"^sha256:([a-f0-9]{64})$", re.IGNORECASE)
_MAX_BYTES = 16 * 1024 * 1024


def normalize_digest_ref(ref: str) -> str:
    cleaned = ref.strip()
    if _DIGEST_RE.match(cleaned):
        return f"sha256:{cleaned.split(':', 1)[1].lower()}"
    if re.fullmatch(r"[a-f0-9]{64}", cleaned, flags=re.IGNORECASE):
        return f"sha256:{cleaned.lower()}"
    raise ValueError("artifact ref must be sha256:<64 hex chars>")


def artifact_blob_exists(digest_ref: str, artifacts_dir: Path) -> bool:
    try:
        path = artifact_path(artifacts_dir, digest_ref)
    except ValueError:
        return False
    return path.is_file()


def validate_deploy_artifact_ref(artifact_ref: str, artifacts_dir: Path) -> str:
    """Normalize sha256 refs and optionally require a stored blob."""
    import os

    cleaned = artifact_ref.strip()
    if not cleaned:
        raise ValueError("artifact_ref is required")
    try:
        normalized = normalize_digest_ref(cleaned)
    except ValueError:
        return cleaned
    require_blob = os.environ.get("AGENTSWARM_DEPLOY_REQUIRE_ARTIFACT_BLOB", "1").strip().lower()
    if require_blob in ("1", "true", "yes", "on") and not artifact_blob_exists(
        normalized, artifacts_dir
    ):
        raise ValueError(f"artifact blob not found: {normalized}")
    return normalized


def artifact_path(artifacts_dir: Path, digest_ref: str) -> Path:
    normalized = normalize_digest_ref(digest_ref)
    digest = normalized.split(":", 1)[1]
    return artifacts_dir / digest[:2] / digest


def store_artifact_blob(content: bytes, artifacts_dir: Path) -> dict[str, int | str]:
    if len(content) > _MAX_BYTES:
        raise ValueError(f"artifact exceeds max size ({_MAX_BYTES} bytes)")
    digest = hashlib.sha256(content).hexdigest()
    digest_ref = f"sha256:{digest}"
    path = artifact_path(artifacts_dir, digest_ref)
    cached = path.is_file()
    if not cached:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return {
        "artifact_ref": digest_ref,
        "bytes": len(content),
        "sha256": digest,
        "cached": cached,
    }


def load_artifact_blob(digest_ref: str, artifacts_dir: Path) -> bytes:
    path = artifact_path(artifacts_dir, digest_ref)
    if not path.is_file():
        raise FileNotFoundError("artifact not found")
    return path.read_bytes()


def enrich_sandbox_tester_result(
    result: dict[str, Any],
    *,
    sandbox_host_owner: str,
    artifacts_dir: Path,
) -> dict[str, Any]:
    """Persist sandbox stdout/stderr bundle and attach refs for trace/UI."""
    if not result.get("sandbox"):
        return result
    enriched = dict(result)
    enriched["sandbox_host_owner"] = sandbox_host_owner
    artifact_key = (
        "build_artifact" if isinstance(enriched.get("build_artifact"), dict) else "run_artifact"
    )
    nested = dict(enriched.get(artifact_key) or {})
    nested["sandbox_host_owner"] = sandbox_host_owner
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    if stdout or stderr:
        bundle = f"=== stdout ===\n{stdout}\n\n=== stderr ===\n{stderr}\n".encode("utf-8")
        stored = store_artifact_blob(bundle, artifacts_dir)
        nested["log_artifact_ref"] = stored["artifact_ref"]
    enriched[artifact_key] = nested
    return enriched
