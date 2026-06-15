from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _find_text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def parse_atom_feed(xml_text: str, *, limit: int = 10) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    entries: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ATOM_NS)[:limit]:
        link = ""
        for child in entry.findall("atom:link", ATOM_NS):
            rel = child.attrib.get("rel", "alternate")
            if rel in ("alternate", ""):
                link = child.attrib.get("href", "")
                break
        title = _find_text(entry.find("atom:title", ATOM_NS))
        updated = _find_text(entry.find("atom:updated", ATOM_NS)) or _find_text(
            entry.find("atom:published", ATOM_NS)
        )
        summary = _find_text(entry.find("atom:summary", ATOM_NS)) or _find_text(
            entry.find("atom:content", ATOM_NS)
        )
        if not link or not title:
            continue
        host = urlparse(link).hostname or "feed"
        entries.append(
            {
                "url": link,
                "title": title,
                "raw_text": summary or title,
                "source": host,
                "published_at": updated or "1970-01-01T00:00:00+00:00",
            }
        )
    return entries
