from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from agentswarm_agents.model_store import (
    download_weight,
    ensure_model_ready,
    model_status,
    model_weight_dir,
    weight_file_path,
)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AGENTSWARM_CLIENT_DATA_DIR", str(tmp_path))
    return tmp_path


def test_model_status_missing_for_weighted_model(data_dir: Path) -> None:
    status = model_status("docker/qwen2.5-coder-3b")
    assert status["state"] == "missing"
    assert status["size_bytes"] == 2104932800


def test_model_status_ready_without_weight(data_dir: Path) -> None:
    status = model_status("llm-mock-v1")
    assert status["state"] == "ready"
    assert status.get("note")


def test_download_weight_writes_manifest(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"gguf-test-bytes-for-model-store"
    expected = hashlib.sha256(payload).hexdigest()
    model_id = "docker/qwen2.5-coder-3b"

    class _FakeStream:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"content-length": str(len(payload))}

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, chunk_size: int = 0):
            del chunk_size
            yield payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "agentswarm_agents.model_store.httpx.stream",
        lambda *args, **kwargs: _FakeStream(),
    )
    monkeypatch.setattr(
        "agentswarm_agents.model_store.get_model_entry",
        lambda mid: {
            "id": model_id,
            "weight": {
                "url": "https://example.test/model.gguf",
                "filename": "model.gguf",
                "sha256": expected,
            },
        },
    )

    path = download_weight(model_id)
    assert path.is_file()
    assert path.read_bytes() == payload
    manifest = json.loads((model_weight_dir(model_id) / "manifest.json").read_text())
    assert manifest["sha256"] == expected


def test_ensure_model_ready_skips_when_present(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model_id = "docker/qwen2.5-coder-3b"
    payload = b"cached-model"
    digest = hashlib.sha256(payload).hexdigest()
    weight = {
        "url": "https://example.test/model.gguf",
        "filename": "model.gguf",
        "sha256": digest,
    }
    path = weight_file_path(model_id, weight)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    (model_weight_dir(model_id) / "manifest.json").write_text(
        json.dumps({"sha256": digest}),
        encoding="utf-8",
    )

    called = {"download": False}

    def _fail_download(*args, **kwargs):
        called["download"] = True
        raise AssertionError("download should not run")

    monkeypatch.setattr("agentswarm_agents.model_store.download_weight", _fail_download)
    resolved = ensure_model_ready(model_id)
    assert resolved == path
    assert called["download"] is False
