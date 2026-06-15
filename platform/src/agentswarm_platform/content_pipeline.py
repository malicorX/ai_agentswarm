from __future__ import annotations

import re
from typing import Any

NEWS_TOPIC_LABELS = [
    "agents",
    "llm",
    "tools",
    "research",
    "open-source",
    "architecture",
]


def validate_scraper_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    entries = result.get("entries")
    if isinstance(entries, list) and entries:
        drafts: list[dict[str, Any]] = []
        for item in entries:
            drafts.append(_validate_draft(item))
        return drafts
    return [_validate_draft(result)]


def _validate_draft(item: dict[str, Any]) -> dict[str, Any]:
    for field in ("url", "title", "raw_text", "source", "published_at"):
        if field not in item or not str(item[field]).strip():
            raise ValueError(f"scraper result missing {field}")
    return {
        "url": str(item["url"]).strip(),
        "title": str(item["title"]).strip(),
        "raw_text": str(item["raw_text"]).strip(),
        "source": str(item["source"]).strip(),
        "published_at": str(item["published_at"]).strip(),
    }


def validate_summarizer_result(result: dict[str, Any]) -> tuple[dict[str, Any], str]:
    summary = result.get("summary")
    draft = result.get("draft")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summarizer result requires summary")
    if not isinstance(draft, dict):
        raise ValueError("summarizer result requires draft object")
    return _validate_draft(draft), summary.strip()


def validate_classifier_result(result: dict[str, Any], payload: dict[str, Any]) -> str:
    label = result.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("classifier result requires label")
    allowed = payload.get("labels") or NEWS_TOPIC_LABELS
    if label not in allowed:
        raise ValueError(f"label must be one of: {', '.join(allowed)}")
    return label


def build_article(*, draft: dict[str, Any], summary: str, label: str, article_id: str | None = None) -> dict[str, Any]:
    slug = re.sub(r"[^a-z0-9]+", "-", draft["title"].lower()).strip("-") or "article"
    article_key = (article_id or slug)[:48].rstrip("-")
    return {
        "id": article_key,
        "title": draft["title"],
        "summary": summary,
        "url": draft["url"],
        "source": draft["source"],
        "published_at": draft["published_at"],
        "topics": [label],
    }


def summarizer_enqueue_spec(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_type": "summarizer.summarize",
        "capability_required": "summarizer",
        "payload": {"draft": draft, "pipeline": True},
    }


def classifier_enqueue_spec(*, draft: dict[str, Any], summary: str) -> dict[str, Any]:
    return {
        "task_type": "classifier.label",
        "capability_required": "classifier",
        "payload": {
            "draft": draft,
            "summary": summary,
            "labels": NEWS_TOPIC_LABELS,
            "pipeline": True,
            "replication": False,
        },
    }


def codewriter_enqueue_spec(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_type": "codewriter.add-article",
        "capability_required": "codewriter",
        "payload": {"article": article},
    }
