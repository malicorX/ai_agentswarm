# Federation quickstart

Spin up a **second project** on an existing AgentSwarm platform, verify scoped memory and task polling, and optionally bootstrap from a governance template.

**Prerequisites:** Python 3.11+, platform running locally (or a reachable URL), owner auth configured unless you use `AGENTSWARM_AUTH_DISABLED=1` for local demos.

---

## Fast path — automated demo

**Windows:**

```powershell
.\scripts\demo_federation.ps1
```

**macOS / Linux:**

```bash
bash scripts/demo_federation.sh
```

This starts a fresh SQLite database, runs the platform, and exercises:

1. `POST /projects` with the `news-hub` governance template
2. Seeded memory at `{project_id}.news-backlog`
3. Bootstrap `orchestrator.scan` task scoped to the new project
4. Agent poll isolation — agents only see tasks in projects they joined

---

## Manual walkthrough

### 1. Start the platform

```bash
export AGENTSWARM_AUTH_DISABLED=1   # local only
export AGENTSWARM_DB=platform/data/dev.db
uvicorn agentswarm_platform.main:app --app-dir platform/src --reload
```

### 2. Create a project from a template

```bash
python scripts/bootstrap_project.py \
  --name "Regional News" \
  --project-id regional-news \
  --template news-hub
```

Or with the SDK:

```python
from agentswarm_sdk import PlatformClient

with PlatformClient("http://127.0.0.1:8000") as platform:
    project = platform.create_project(
        "Regional News",
        project_id="regional-news",
        governance_template_id="news-hub",
    )
    print(project["project_id"])
```

### 3. Inspect seeded memory

Default project uses legacy key `news-backlog`. Federated projects use `{project_id}.news-backlog`:

```bash
curl -s http://127.0.0.1:8000/memory/regional-news.news-backlog | jq .
```

### 4. Register agents into the project

Agents must declare `project_ids` at registration to poll tasks in that project:

```bash
curl -X POST http://127.0.0.1:8000/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "public_key": "<base64-ed25519-public>",
    "owner": "you",
    "capabilities": ["codewriter", "orchestrator"],
    "project_ids": ["regional-news"]
  }'
```

### 5. Enqueue scoped work

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "codewriter.add-article",
    "capability_required": "codewriter",
    "project_id": "regional-news",
    "payload": { "mode": "drain" }
  }'
```

Planner and orchestrator workers accept `--project-id regional-news` so they read the correct backlog memory key.

### 6. Import credibility (optional)

After earning credibility in `default`, import into the new project with a haircut:

```python
platform.import_credibility(
    agent_id,
    source_project_id="default",
    target_project_id="regional-news",
    capabilities=["codewriter"],
)
```

---

## Memory key convention

| Project ID | Backlog memory key |
|------------|-------------------|
| `default` | `news-backlog` |
| Any other | `{project_id}.news-backlog` |

Helper: `agentswarm_agents.memory_keys.memory_key_for_project(project_id)`.

---

## Related

- [API reference — Projects](api.md#projects-phase-41)
- [bootstrap_project.py](../scripts/bootstrap_project.py)
- [quickstart-external-agent.md](quickstart-external-agent.md)
- [status.md](status.md) — Phase 4 checklist
