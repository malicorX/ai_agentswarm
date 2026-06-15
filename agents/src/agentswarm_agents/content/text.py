from __future__ import annotations

import re
from typing import Any


def slugify(text: str, *, max_length: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        slug = "article"
    return slug[:max_length].rstrip("-")


def summarize_text(text: str, *, max_chars: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    cut = cleaned[:max_chars]
    boundary = cut.rfind(". ")
    if boundary > max_chars // 2:
        return cut[: boundary + 1].strip()
    return cut.rstrip() + "…"


def classify_topics(text: str, labels: list[str]) -> str:
    haystack = text.lower()
    for label in labels:
        if label.lower() in haystack:
            return label
    return labels[0] if labels else "news"


def strip_html(html: str) -> str:
    without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", text).strip()
