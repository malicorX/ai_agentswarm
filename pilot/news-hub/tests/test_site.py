from pathlib import Path
import json

PILOT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("id", "title", "summary", "url", "source", "published_at")


def test_index_has_title():
    html = (PILOT_ROOT / "index.html").read_text(encoding="utf-8")
    assert "<title>AI News Hub</title>" in html
    assert "AI News Hub" in html


def test_agentswarm_marker_present():
    html = (PILOT_ROOT / "index.html").read_text(encoding="utf-8")
    assert "<!-- agentswarm -->" in html


def test_feed_markup_present():
    html = (PILOT_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="feed"' in html
    assert "data/articles.json" in html


def test_articles_json_valid():
    path = PILOT_ROOT / "data" / "articles.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    articles = data["articles"]
    assert len(articles) >= 1
    for article in articles:
        for field in REQUIRED:
            assert field in article and article[field]


def test_article_ids_unique():
    path = PILOT_ROOT / "data" / "articles.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [a["id"] for a in data["articles"]]
    assert len(ids) == len(set(ids))
