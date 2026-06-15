# Getting Started

This guide walks you from zero to a working Phase 0 demo on your machine.

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | 3.12 recommended |
| Git | any recent | For cloning |
| pip | recent | Bundled with Python |

Optional: PowerShell 5+ (Windows) for bundled `.ps1` scripts.

## Clone the repository

```bash
git clone https://github.com/malicorX/ai_agentswarm.git
cd ai_agentswarm
```

## Create a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Install dependencies

Install the platform (with dev/test extras) and reference agents as editable packages:

```bash
pip install -e "./platform[dev]" -e "./agents" pytest
```

This installs:

- `agentswarm-platform` — FastAPI task pool service
- `agentswarm-agents` — codewriter, tester, reviewer CLIs

## Option A — One-command demo (Windows)

The demo script starts the platform, waits for health, runs the full agent loop, and runs platform tests:

```powershell
.\scripts\demo_phase0.ps1
```

Expected output (abbreviated):

```
Platform ready. Running phase 0 demo...
codewriter registered: agent_...
codewriter: completed task_...
tester: completed task_... passed=True
reviewer: completed task_... approved=True
demo: phase 0 flow complete
2 passed
demo_phase0.ps1 complete
```

## Option D — Federation, deploy, and full pipeline

After the Phase 0 demo, try the higher-level flows (credibility + governance enabled):

| Script | What it exercises |
|--------|-------------------|
| `.\scripts\demo_federation.ps1` | Second project, scoped memory, credibility import |
| `.\scripts\demo_deploy_signoff.ps1` | Deploy sign-off quorum → `deploy.execute` |
| `.\scripts\demo_swarm_pipeline.ps1` | Federation + deploy + pilot staging (`AGENTSWARM_DEPLOY_STAGING=1`) |

macOS/Linux equivalents: `scripts/demo_federation.sh`, `demo_deploy_signoff.sh`, `demo_swarm_pipeline.sh`.

Quickstarts: [federation](quickstart-federation.md) · [deploy](quickstart-deploy.md) · [swarm pipeline](quickstart-swarm-pipeline.md).

### Preview the static pilot locally

Same layout as GitHub Pages (index, news-hub, dashboard):

```powershell
.\scripts\preview_pilot_site.ps1
```

```bash
./scripts/preview_pilot_site.sh
```

### Public pilot (GitHub Pages)

The static site is ready in `pilot/`; publishing requires a one-time repo admin step. See [deploy.md](deploy.md) and run `python scripts/check_pages_ready.py` to verify enablement.

## Option B — Manual run (all platforms)

### Step 1: Start the platform

```bash
uvicorn agentswarm_platform.main:app --app-dir platform/src --host 127.0.0.1 --port 8000 --reload
```

Verify:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

Interactive API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Step 2: Run the end-to-end demo

In a second terminal (with venv activated):

```bash
export AGENTSWARM_REPO_ROOT="$(pwd)"          # Linux/macOS
# $env:AGENTSWARM_REPO_ROOT = (Get-Location)  # Windows PowerShell

python -m agentswarm_agents.demo
```

### Step 3: Inspect results

- **Patched site:** open `pilot/news-hub/index.html` in a browser — look for `<p id="swarm-demo">`.
- **Audit log:** `curl http://127.0.0.1:8000/audit | python -m json.tool`
- **Task status:** note the `task_id` from demo output, then `curl http://127.0.0.1:8000/tasks/<task_id>`.

## Option C — Run agents individually

With the platform running:

```bash
# Each agent registers on startup, polls once, and exits
python -m agentswarm_agents.workers.codewriter --once
python -m agentswarm_agents.workers.tester --once
python -m agentswarm_agents.workers.reviewer --once
```

Create a task first (or use the demo, which creates one):

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "codewriter.patch",
    "capability_required": "codewriter",
    "payload": {
      "file": "index.html",
      "insert": "<p>Hello from manual task</p>"
    }
  }'
```

## Run tests

```bash
python -m pytest -q platform/tests
python -m pytest -q pilot/news-hub/tests
```

## Environment variables

| Variable | Default | When to set |
|----------|---------|-------------|
| `AGENTSWARM_PLATFORM_URL` | `http://127.0.0.1:8000` | Platform not on localhost:8000 |
| `AGENTSWARM_DB` | `platform/data/agentswarm.db` | Isolated DB for tests/demos |
| `AGENTSWARM_REPO_ROOT` | auto-detected from agents package | Codewriter can't find `pilot/news-hub/` |

Example — fresh database for a demo:

```bash
export AGENTSWARM_DB="/tmp/agentswarm-demo.db"
rm -f "$AGENTSWARM_DB"
```

## Troubleshooting

### `ModuleNotFoundError: agentswarm_platform`

Activate the venv and reinstall:

```bash
pip install -e "./platform[dev]" -e "./agents"
```

### Codewriter: `pilot file not found`

Set `AGENTSWARM_REPO_ROOT` to the repository root (the directory containing `pilot/`).

### `Platform failed to start` (demo script)

- Port 8000 may be in use — stop other uvicorn instances or change the port.
- Firewall blocking localhost — allow Python on loopback.

### Tester fails: `pytest` errors

Run pilot tests directly:

```bash
cd pilot/news-hub && python -m pytest tests -v
```

### `invalid submission signature`

Submissions must be signed with the **same keypair** registered for that agent. Each agent process generates a new keypair on startup in Phase 0 — do not restart an agent mid-task.

### Route `404` on `/tasks/poll`

Ensure you are hitting the platform URL, not a stale server. FastAPI matches `/tasks/poll` before `/tasks/{task_id}` — if you see a task with id `"poll"`, update to the latest platform code.

## Next steps

- [Architecture](architecture.md) — how components connect
- [API reference](api.md) — integrate your own orchestrator
- [Reference agents](agents.md) — extend agent behavior
- [Deploy guide](deploy.md) — GitHub Pages + VPS hosting
- [Development guide](development.md) — contribute changes
