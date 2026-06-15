from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "record_pages_url.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("record_pages_url", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_pages_url_updates_docs(tmp_path: Path) -> None:
    mod = _load_module()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "status.md").write_text(
        "  - [ ] Enable GitHub Pages in repo settings (admin) + record live URL\n",
        encoding="utf-8",
    )
    (docs / "deploy.md").write_text(
        "**Expected URL (once enabled):** `https://example.github.io/repo`\n",
        encoding="utf-8",
    )

    url = "https://malicorx.github.io/ai_agentswarm"
    mod.record_pages_url(tmp_path, url)

    status = (docs / "status.md").read_text(encoding="utf-8")
    deploy = (docs / "deploy.md").read_text(encoding="utf-8")
    assert f"[x] Enable GitHub Pages" in status
    assert url in status
    assert f"**Live URL:** `{url}/`" in deploy


def test_record_pages_url_rejects_non_https(tmp_path: Path) -> None:
    mod = _load_module()
    with pytest.raises(ValueError, match="https"):
        mod.record_pages_url(tmp_path, "http://insecure.example")
