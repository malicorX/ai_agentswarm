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
        "- [ ] Manual deploy by human maintainer\n"
        "  - [ ] Enable GitHub Pages in repo settings (admin) + record live URL\n",
        encoding="utf-8",
    )
    (docs / "deploy.md").write_text(
        "**Expected URL (once enabled):** `https://example.github.io/repo`\n"
        "- [ ] Pilot static site hosted (URL recorded below)\n"
        "| AI News Hub pilot | https://example.github.io/repo/news-hub/ (pending) | |\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "| **Public pilot** | **Pending** — enable Pages |\n",
        encoding="utf-8",
    )

    url = "https://malicorx.github.io/ai_agentswarm"
    mod.record_pages_url(tmp_path, url, recorded_at="2026-06-15")

    status = (docs / "status.md").read_text(encoding="utf-8")
    deploy = (docs / "deploy.md").read_text(encoding="utf-8")
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "[x] Manual deploy" in status
    assert f"[x] Enable GitHub Pages" in status
    assert url in status
    assert f"**Live URL:** `{url}/`" in deploy
    assert f"| Pilot site (GitHub Pages) | {url}/ | 2026-06-15 |" in deploy
    assert "2026-06-15" in deploy
    assert "**Pending**" in readme


def test_record_pages_url_rejects_non_https(tmp_path: Path) -> None:
    mod = _load_module()
    with pytest.raises(ValueError, match="https"):
        mod.record_pages_url(tmp_path, "http://insecure.example")
