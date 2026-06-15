from __future__ import annotations

from agentswarm_platform.content_pipeline import (
    build_article,
    classifier_enqueue_spec,
    codewriter_enqueue_spec,
    summarizer_enqueue_spec,
    validate_scraper_result,
    validate_summarizer_result,
)


def test_validate_scraper_and_chain_specs() -> None:
    drafts = validate_scraper_result(
        {
            "url": "https://example.com/a",
            "title": "Title",
            "raw_text": "Body",
            "source": "example.com",
            "published_at": "2026-06-15T10:00:00+00:00",
        }
    )
    assert len(drafts) == 1
    spec = summarizer_enqueue_spec(drafts[0])
    assert spec["task_type"] == "summarizer.summarize"


def test_summarizer_to_classifier_to_article() -> None:
    draft = {
        "url": "https://example.com/a",
        "title": "Agents update",
        "raw_text": "Long text about agents",
        "source": "example.com",
        "published_at": "2026-06-15T10:00:00+00:00",
    }
    validated_draft, summary = validate_summarizer_result({"draft": draft, "summary": "Short"})
    spec = classifier_enqueue_spec(draft=validated_draft, summary=summary)
    assert spec["payload"]["pipeline"] is True
    article = build_article(draft=validated_draft, summary=summary, label="agents")
    writer = codewriter_enqueue_spec(article)
    assert writer["task_type"] == "codewriter.add-article"
    assert writer["payload"]["article"]["topics"] == ["agents"]
