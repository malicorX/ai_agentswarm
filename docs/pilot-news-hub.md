# AI News Hub Pilot

The **AI News Hub** is AgentSwarm's bootstrap project — a website that aggregates, classifies, and summarizes AI-development news. Phase 0 implements a minimal static scaffold; later phases add content pipelines and deployment.

**Location:** `pilot/news-hub/`

## Long-term vision (ROADMAP §2)

The full pilot exercises:

| Role | Future agent types |
|------|-------------------|
| Gather news | `scraper`, `researcher` |
| Transform content | `summarizer`, `classifier`, `fact-checker` |
| Build the site | `codewriter`, `designer`, `architect` |
| Assure quality | `tester`, `reviewer`, `security-auditor` |
| Ship | `deployer` |
| Coordinate | `planner`, `orchestrator` |

If the swarm can sustainably build and operate this site, the same platform can target any shared project.

## Phase 0 scope

What exists today:

```
pilot/news-hub/
├── index.html              # Landing page + JS feed loader
├── data/articles.json      # Swarm-maintained article feed
├── schema/news-item.json   # Article JSON schema
├── tests/test_site.py
└── README.md
```

Agents can **patch HTML** (`codewriter.patch`) or **append articles** (`codewriter.add-article`). The tester runs pytest. The reviewer gates merge to `verified`.

**Not yet:** scrapers, CMS database, LLM summarization.

## The `<!-- agentswarm -->` marker

Codewriter tasks insert content relative to an HTML comment marker in `index.html`:

```html
<main>
  <p>Welcome...</p>
  <!-- agentswarm -->
</main>
```

After a successful codewriter task:

```html
  <!-- agentswarm -->
<p id="swarm-demo">Patched by AgentSwarm codewriter.</p>
```

This gives agents a **safe, deterministic edit point** without a full diff engine in Phase 0.

Then run agents (see [agents.md](agents.md)).

## Article feed (`codewriter.add-article`)

Articles live in `data/articles.json`. The homepage loads and renders them via `fetch("data/articles.json")` — serve over HTTP (GitHub Pages, `python -m http.server`, or nginx).

**Schema:** `schema/news-item.json`

**Enqueue via maintainer script:**

```bash
python scripts/enqueue_task.py add-article \
  --id my-story \
  --title "Story title" \
  --summary "One paragraph." \
  --url "https://example.com/article" \
  --source "Example Blog" \
  --topics "ai,agents"
```

Then run `agentswarm-codewriter --once` (and tester, reviewer).

## Sample patch payload

```json
{
  "task_type": "codewriter.patch",
  "capability_required": "codewriter",
  "payload": {
    "file": "index.html",
    "insert": "<p id=\"feature\">New section</p>",
    "marker": "<!-- agentswarm -->"
  }
}
```

Create via API:

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Content-Type: application/json" \
  -d @task.json
```

Then run agents (see [agents.md](agents.md)).

## Tests

```bash
cd pilot/news-hub
python -m pytest tests -v
```

Current tests verify:

- Page title contains "AI News Hub"
- `<!-- agentswarm -->` marker is present (required for codewriter)

**Extend tests** as the pilot grows — e.g. check for new sections, link validity, accessibility.

## Viewing changes

Open `index.html` directly in a browser, or serve locally:

```bash
cd pilot/news-hub
python -m http.server 8080
# http://localhost:8080
```

## Future milestones

| Milestone | Phase | Description |
|-----------|-------|-------------|
| Static scaffold | 0 | ✅ Current |
| Content model + JSON feed | 1–2 | Structured news items |
| Scraper agents | 2+ | Pull from declared sources |
| Summarizer pipeline | 2+ | LLM summaries with verification |
| Staging deploy | 2+ | Deployer agent + human sign-off |
| Production | 3+ | Automated deploy with multi-agent sign-off |

Track progress in [status.md](status.md).

## Related

- [Reference agents](agents.md)
- [ROADMAP.md §2](../ROADMAP.md#2-the-pilot-project)
- [Getting started](getting-started.md)
