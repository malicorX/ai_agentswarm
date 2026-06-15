from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "record_pilot_url.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("record_pilot_url", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_pilot_url_theebie_updates_docs(tmp_path: Path) -> None:
    mod = _load_module()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "status.md").write_text(
        "- [ ] Manual deploy by human maintainer\n"
        "  - [ ] Host pilot static site on theebie.de (`/sites/agentswarm/`) + record live URL\n"
        "  - [ ] (Optional) GitHub Pages for forks — enable in repo settings + record URL\n",
        encoding="utf-8",
    )
    (docs / "deploy.md").write_text(
        "**Maintainer URL (theebie.de):** `https://theebie.de/sites/agentswarm`\n"
        "- [ ] Pilot static site hosted (URL recorded below)\n"
        "| AI News Hub pilot | pending | |\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "| **Public pilot** | **Pending** — deploy |\n",
        encoding="utf-8",
    )

    url = "https://theebie.de/sites/agentswarm"
    mod.record_pilot_url(tmp_path, url, recorded_at="2026-06-15")

    status = (docs / "status.md").read_text(encoding="utf-8")
    assert "[x] Manual deploy" in status
    assert "[x] Host pilot static site on theebie.de" in status
    assert url in status
    assert (docs / "deploy.md").read_text(encoding="utf-8").count(url) >= 2


def test_record_pilot_url_github_pages_preserves_theebie(tmp_path: Path) -> None:
    mod = _load_module()
    docs = tmp_path / "docs"
    docs.mkdir()
    theebie = "https://theebie.de/sites/agentswarm"
    pages = "https://malicorx.github.io/ai_agentswarm"
    (docs / "status.md").write_text(
        "- [x] Manual deploy by human maintainer\n"
        f"  - [x] Host pilot static site on theebie.de (`/sites/agentswarm/`) + record live URL → {theebie}\n"
        "  - [ ] (Optional) GitHub Pages for forks — enable in repo settings + record URL\n"
        "**Optional next (operator):** GitHub Pages for forks — [deploy.md](deploy.md) Option B.\n",
        encoding="utf-8",
    )
    (docs / "deploy.md").write_text(
        f"**Maintainer URL (theebie.de):** `{theebie}/`\n"
        f"| AI News Hub pilot | {theebie}/news-hub/ | 2026-06-15 |\n"
        "forks may use `https://<user>.github.io/ai_agentswarm`\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        f"| **Public pilot** | [{theebie}/]({theebie}/) · [dashboard]({theebie}/dashboard/) |\n",
        encoding="utf-8",
    )

    mod.record_pilot_url(tmp_path, pages, recorded_at="2026-06-15")

    status = (docs / "status.md").read_text(encoding="utf-8")
    deploy = (docs / "deploy.md").read_text(encoding="utf-8")
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "[x] (Optional) GitHub Pages" in status
    assert pages in status
    assert theebie in deploy
    assert f"| Pilot site (GitHub Pages) | {pages}/ | 2026-06-15 |" in deploy
    assert theebie in readme
    assert pages not in readme
