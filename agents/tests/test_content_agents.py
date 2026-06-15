from __future__ import annotations

from agentswarm_agents.content.rss import parse_atom_feed
from agentswarm_agents.content.text import classify_topics, slugify, summarize_text


def test_slugify_normalizes_title() -> None:
    assert slugify("Hello World!") == "hello-world"


def test_summarize_text_truncates_long_body() -> None:
    text = "Word. " * 200
    summary = summarize_text(text, max_chars=80)
    assert len(summary) <= 81
    assert summary.endswith(("…", "."))


def test_classify_topics_prefers_keyword_match() -> None:
    label = classify_topics("New LLM benchmark results", ["agents", "llm", "tools"])
    assert label == "llm"


def test_parse_atom_feed_extracts_entries() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Sample</title>
        <link href="https://example.com/post" rel="alternate"/>
        <updated>2026-06-15T10:00:00Z</updated>
        <summary>Body text</summary>
      </entry>
    </feed>
    """
    entries = parse_atom_feed(xml)
    assert len(entries) == 1
    assert entries[0]["url"] == "https://example.com/post"
    assert entries[0]["title"] == "Sample"
