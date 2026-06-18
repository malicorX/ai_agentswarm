"""Download and verify allowlisted model weights into the client data directory."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from agentswarm_agents.client_data_dir import models_dir
from agentswarm_agents.model_allowlist import get_model_entry

ProgressCallback = Callable[[str, int, int | None], None]


def _sanitize_model_id(model_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", model_id).strip("-")
    return safe or "model"


def model_weight_dir(model_id: str) -> Path:
    return models_dir() / _sanitize_model_id(model_id)


def manifest_path(model_id: str) -> Path:
    return model_weight_dir(model_id) / "manifest.json"


def weight_spec(model_entry: dict[str, Any]) -> dict[str, Any] | None:
    weight = model_entry.get("weight")
    if not isinstance(weight, dict):
        return None
    url = str(weight.get("url", "")).strip()
    if not url:
        return None
    return weight


def worker_image_for_model(model_entry: dict[str, Any], *, default: str) -> str:
    image = model_entry.get("worker_image")
    if isinstance(image, str) and image.strip():
        return image.strip()
    return default


def weight_file_path(model_id: str, weight: dict[str, Any]) -> Path:
    filename = str(weight.get("filename", "model.gguf")).strip() or "model.gguf"
    return model_weight_dir(model_id) / filename


def load_manifest(model_id: str) -> dict[str, Any] | None:
    path = manifest_path(model_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def write_manifest(model_id: str, manifest: dict[str, Any]) -> None:
    directory = model_weight_dir(model_id)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path(model_id).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_status(model_id: str) -> dict[str, Any]:
    entry = get_model_entry(model_id)
    if entry is None:
        return {"model_id": model_id, "state": "unknown"}
    weight = weight_spec(entry)
    if weight is None:
        return {
            "model_id": model_id,
            "state": "ready",
            "runtime": entry.get("runtime"),
            "note": "no weight download required",
        }
    path = weight_file_path(model_id, weight)
    manifest = load_manifest(model_id)
    if path.is_file() and manifest and manifest.get("sha256") == sha256_file(path):
        return {
            "model_id": model_id,
            "state": "ready",
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": manifest.get("sha256"),
        }
    if path.is_file():
        return {
            "model_id": model_id,
            "state": "needs_verify",
            "path": str(path),
            "bytes": path.stat().st_size,
        }
    return {
        "model_id": model_id,
        "state": "missing",
        "size_bytes": weight.get("size_bytes"),
        "url": weight.get("url"),
    }


def _noop_progress(phase: str, done: int, total: int | None) -> None:
    return None


def _verify_weight_file(path: Path, weight: dict[str, Any]) -> str:
    digest = sha256_file(path)
    expected = str(weight.get("sha256", "")).strip().lower()
    if expected and digest.lower() != expected:
        raise ValueError(
            f"model weight sha256 mismatch (expected {expected[:12]}…, got {digest[:12]}…)"
        )
    return digest


def download_weight(
    model_id: str,
    *,
    on_progress: ProgressCallback | None = None,
    timeout_sec: float = 3600.0,
) -> Path:
    entry = get_model_entry(model_id)
    if entry is None:
        raise ValueError(f"unknown model_id {model_id!r}")
    weight = weight_spec(entry)
    if weight is None:
        raise ValueError(f"model {model_id!r} has no weight artifact")

    directory = model_weight_dir(model_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = weight_file_path(model_id, weight)
    partial = destination.with_suffix(destination.suffix + ".partial")
    url = str(weight["url"])
    progress = on_progress or _noop_progress

    progress("connecting", 0, weight.get("size_bytes"))
    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout_sec) as response:
        response.raise_for_status()
        total = weight.get("size_bytes")
        if total is None:
            content_length = response.headers.get("content-length")
            if content_length and content_length.isdigit():
                total = int(content_length)
        downloaded = 0
        digest = hashlib.sha256()
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                progress("downloading", downloaded, total if isinstance(total, int) else None)

    partial.replace(destination)
    file_digest = digest.hexdigest()
    expected = str(weight.get("sha256", "")).strip().lower()
    if expected and file_digest.lower() != expected:
        destination.unlink(missing_ok=True)
        raise ValueError(
            f"downloaded model sha256 mismatch (expected {expected[:12]}…, got {file_digest[:12]}…)"
        )
    if not expected:
        file_digest = sha256_file(destination)

    write_manifest(
        model_id,
        {
            "model_id": model_id,
            "filename": destination.name,
            "sha256": file_digest,
            "size_bytes": destination.stat().st_size,
            "url": url,
            "downloaded_at": datetime.now(UTC).isoformat(),
        },
    )
    progress("ready", destination.stat().st_size, destination.stat().st_size)
    return destination


def ensure_model_ready(
    model_id: str,
    *,
    on_progress: ProgressCallback | None = None,
) -> Path | None:
    """Ensure weight file exists and verifies; download when missing."""
    if os.environ.get("AGENTSWARM_MODEL_SKIP_DOWNLOAD", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        entry = get_model_entry(model_id)
        if entry is None:
            raise ValueError(f"unknown model_id {model_id!r}")
        weight = weight_spec(entry)
        if weight is None:
            return None
        path = weight_file_path(model_id, weight)
        if not path.is_file():
            raise FileNotFoundError(
                f"AGENTSWARM_MODEL_SKIP_DOWNLOAD is set but weight missing: {path}"
            )
        _verify_weight_file(path, weight)
        return path

    status = model_status(model_id)
    if status["state"] == "ready":
        return Path(str(status["path"]))
    if status["state"] == "needs_verify":
        entry = get_model_entry(model_id)
        assert entry is not None
        weight = weight_spec(entry)
        assert weight is not None
        path = Path(str(status["path"]))
        digest = _verify_weight_file(path, weight)
        write_manifest(
            model_id,
            {
                "model_id": model_id,
                "filename": path.name,
                "sha256": digest,
                "size_bytes": path.stat().st_size,
                "url": weight.get("url"),
                "downloaded_at": datetime.now(UTC).isoformat(),
            },
        )
        return path
    return download_weight(model_id, on_progress=on_progress)


def ensure_model_for_entry(
    model_entry: dict[str, Any],
    *,
    on_progress: ProgressCallback | None = None,
) -> Path | None:
    model_id = str(model_entry["id"])
    weight = weight_spec(model_entry)
    if weight is None:
        return None
    return ensure_model_ready(model_id, on_progress=on_progress)
