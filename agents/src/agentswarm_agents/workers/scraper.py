from __future__ import annotations

import argparse
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from agentswarm_agents.client import platform_url
from agentswarm_agents.content.rss import parse_atom_feed
from agentswarm_agents.content.text import strip_html
from agentswarm_agents.identity import connect_agent


def _host_allowed(url: str, allowlist: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == allowed.lower() or host.endswith(f".{allowed.lower()}") for allowed in allowlist)


def fetch_page(url: str, *, allowlist: list[str]) -> dict[str, Any]:
    if not _host_allowed(url, allowlist):
        raise ValueError(f"host not in egress allowlist: {url}")
    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    text = response.text
    if "xml" in content_type or url.endswith(".atom") or "<feed" in text[:200]:
        entries = parse_atom_feed(text, limit=5)
        if not entries:
            raise ValueError("feed contained no entries")
        return {"entries": entries, "mode": "feed"}
    title = url
    if "<title>" in text.lower():
        start = text.lower().index("<title>") + len("<title>")
        end = text.lower().find("</title>", start)
        if end > start:
            title = strip_html(text[start:end])
    raw_text = strip_html(text)
    host = urlparse(url).hostname or "web"
    return {
        "url": str(response.url),
        "title": title,
        "raw_text": raw_text[:4000],
        "source": host,
        "published_at": "1970-01-01T00:00:00+00:00",
        "mode": "page",
    }


def execute_task(task: dict[str, Any], *, allowlist: list[str]) -> dict[str, Any]:
    payload = task["payload"]
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("scraper.fetch requires payload.url")
    return fetch_page(url.strip(), allowlist=allowlist)


def run_once(client, allowlist: list[str]) -> bool:
    tasks = client.poll_tasks(capability="scraper")
    if not tasks:
        return False
    task = tasks[0]
    claim_token = client.claim(task["task_id"])
    result = execute_task(task, allowlist=allowlist)
    client.submit(claim_token, task["task_id"], result)
    count = len(result.get("entries", [result]))
    print(f"scraper: completed {task['task_id']} ({count} draft(s))")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentSwarm scraper agent")
    parser.add_argument("--agent-name", default="scraper")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument(
        "--egress",
        default=os.environ.get("AGENTSWARM_SCRAPER_EGRESS", "github.com,example.com"),
        help="Comma-separated allowed hosts",
    )
    args = parser.parse_args()
    allowlist = [host.strip() for host in args.egress.split(",") if host.strip()]
    client = connect_agent(
        agent_name=args.agent_name,
        owner="news-scraper",
        capabilities=["scraper"],
        base_url=platform_url(),
        egress_allowlist=allowlist,
    )
    print(f"scraper: connected as {client.agent_id}")
    if args.once:
        if not run_once(client, allowlist):
            print("scraper: no tasks")
        return
    while True:
        try:
            if run_once(client, allowlist):
                continue
        except Exception as exc:  # noqa: BLE001 — keep polling after transient API errors
            print(f"scraper: error: {exc}")
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
