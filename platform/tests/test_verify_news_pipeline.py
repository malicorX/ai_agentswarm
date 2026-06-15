from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_news_pipeline.py"
PIPELINE_SCRIPT = REPO_ROOT / "scripts" / "news_feed_pipeline.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_feed_config_reads_repo_config() -> None:
    mod = _load_module(PIPELINE_SCRIPT, "news_feed_pipeline")
    feeds = mod.load_feed_config(REPO_ROOT / "config" / "news-feeds.json")
    assert len(feeds) >= 1
    assert "url" in feeds[0]


def test_verify_news_pipeline_enqueue_only(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module(VERIFY_SCRIPT, "verify_news_pipeline_test")
    summary_resp = MagicMock()
    summary_resp.json.return_value = {"tasks": {"verified": 12}}
    summary_resp.raise_for_status = MagicMock()

    monkeypatch.setattr(
        mod,
        "enqueue_news_feeds",
        lambda _base, **kwargs: ["task_a", "task_b"],
    )

    with patch.object(mod.httpx, "get", return_value=summary_resp):
        result = mod.verify_news_pipeline(
            "https://theebie.de/agentswarm/api",
            enqueue_only=True,
        )

    assert result["mode"] == "enqueue_only"
    assert result["verified_before"] == "12"
    assert result["enqueued_tasks"] == "2"
    assert result["task_ids"] == "task_a,task_b"


def test_verify_news_pipeline_waits_for_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module(VERIFY_SCRIPT, "verify_news_pipeline_wait")
    first = MagicMock()
    first.json.return_value = {"tasks": {"verified": 5}}
    first.raise_for_status = MagicMock()
    second = MagicMock()
    second.json.return_value = {"tasks": {"verified": 6}}

    monkeypatch.setattr(mod, "enqueue_news_feeds", lambda _base, **kwargs: ["task_1"])
    monkeypatch.setattr(mod.time, "sleep", lambda _sec: None)
    times = iter([0.0, 1.0, 2.0])
    monkeypatch.setattr(mod.time, "time", lambda: next(times))

    with patch.object(mod.httpx, "get", side_effect=[first, second]):
        result = mod.verify_news_pipeline("https://example.test/api", timeout_sec=30.0)

    assert result["mode"] == "verified"
    assert result["verified_after"] == "6"


def test_verify_news_pipeline_timeout_includes_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module(VERIFY_SCRIPT, "verify_news_pipeline_timeout")
    summary = MagicMock()
    summary.json.return_value = {"tasks": {"verified": 3, "claimed": 1}}
    summary.raise_for_status = MagicMock()

    monkeypatch.setattr(mod, "enqueue_news_feeds", lambda _base, **kwargs: ["task_1"])
    monkeypatch.setattr(mod.time, "sleep", lambda _sec: None)
    times = iter([0.0, 1000.0])
    monkeypatch.setattr(mod.time, "time", lambda: next(times))

    with patch.object(mod.httpx, "get", return_value=summary):
        with pytest.raises(RuntimeError, match="verified stayed at 3"):
            mod.verify_news_pipeline("https://example.test/api", timeout_sec=1.0)
