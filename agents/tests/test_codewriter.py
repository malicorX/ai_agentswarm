"""Tests for codewriter add-article handler."""

import json
import tempfile
from pathlib import Path

import pytest

from agentswarm_agents.workers import codewriter


@pytest.fixture
def pilot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pilot_root = tmp_path / "news-hub"
    (pilot_root / "data").mkdir(parents=True)
    (pilot_root / "data" / "articles.json").write_text(
        json.dumps({"articles": []}) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(codewriter, "pilot_dir", lambda: str(pilot_root))
    return pilot_root


def test_add_article_appends(pilot: Path) -> None:
    result = codewriter.add_article(
        {
            "article": {
                "id": "test-item",
                "title": "Test",
                "summary": "Summary text",
                "url": "https://example.com/a",
                "source": "Test",
                "published_at": "2026-06-13T12:00:00+00:00",
                "topics": ["test"],
            }
        }
    )
    assert result["article_id"] == "test-item"
    data = json.loads((pilot / "data" / "articles.json").read_text(encoding="utf-8"))
    assert len(data["articles"]) == 1


def test_add_article_rejects_duplicate(pilot: Path) -> None:
    payload = {
        "article": {
            "id": "dup",
            "title": "T",
            "summary": "S",
            "url": "https://example.com",
            "source": "X",
            "published_at": "2026-06-13T12:00:00+00:00",
        }
    }
    codewriter.add_article(payload)
    with pytest.raises(ValueError, match="duplicate"):
        codewriter.add_article(payload)
