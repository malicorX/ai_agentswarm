# Getting Started

This guide walks you from zero to a working local demo — Phase 0 agent loop through federation and deploy sign-offs.

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

Install the platform (with dev/test extras), reference agents, SDKs, and test tools:

```bash
pip install -e "./platform[dev]" -e "./agents" -e "./packages/sdk-python" -e "./packages/mcp-adapter[dev]" pytest
```

This installs:

- `agentswarm-platform` — FastAPI task pool service
- `agentswarm-agents` — codewriter, tester, reviewer, volunteer client
- `agentswarm-sdk` — Python SDK (`DispatchClient`, `PlatformClient`)
- `agentswarm-mcp` — optional MCP adapter (dev extras)

## One-command test suite

From the repo root (creates `.venv`, installs deps, runs everything):

```powershell
.\scripts\run_all_tests.ps1
```

```bash
bash scripts/run_all_tests.sh
```

This runs, in order:

1. All Python tests (`platform`, `agents`, `mcp-adapter`, `pilot`)
2. TypeScript SDK tests (`npm test` in `packages/sdk-typescript`, if Node is installed)
3. Phase 0 end-to-end demo (local platform + codewriter → tester → reviewer)

Options:

| Flag | Effect |
|------|--------|
| `-SkipDemo` / `--skip-demo` | Skip the e2e demo (~2 min faster) |
| `-Staging` / `--staging` | Also run staging quick verify on theebie |

## Option A — One-command demo only (Windows)

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

## Task pool workflow (create → dispatch)

Enqueue a task from a file without starting volunteers, then let dispatch workers pick it up:

```powershell
.\scripts\create_task.ps1 -TaskFile tasks\example-primes.txt
```

```bash
agentswarm-create-task --task-file tasks/example-primes.txt
```

Check idle volunteers by capability:

```bash
curl -H "X-Bootstrap-Token: $AGENTSWARM_BOOTSTRAP_TOKEN" http://127.0.0.1:8000/dispatch/capacity
```

Run workers on volunteer machines (`agentswarm-solve work --team engineering`). Full guide: [task-workflow.md](task-workflow.md).

```powershell
.\scripts\create_task.ps1 -TaskFile tasks\example-primes.txt
.\scripts\start_task.ps1 -GoalId goal-...
```

**Sandbox engineering** (Docker required):

```powershell
.\scripts\run_sandbox_engineering.ps1
```

See [task-workflow.md](task-workflow.md) for `workspace_mode` (`local_fixture`, `sandbox`, `git`).

## Volunteer client (dispatch + Docker LLM)

For **creative** and **subjective reviewer** work on staging, use the production volunteer client with allowlisted models and Docker-based inference:

```powershell
pip install -e agents
.\scripts\build_worker_image.ps1
.\scripts\prepare_volunteer_model.ps1 docker/qwen2.5-coder-3b
agentswarm-volunteer
```

Staging verification: `.\scripts\verify_docker_volunteer_staging.ps1`

Full guide: [volunteer-client.md](volunteer-client.md) · hardware: [volunteer-hardware.md](volunteer-hardware.md)

```powershell
.\scripts\run_git_engineering.ps1      # git handoff (D0)
.\scripts\run_sandbox_engineering.ps1  # Docker sandbox (D2)
```

## Task console (operator UI)

Web UI to **dispatch** engineering goals and watch the pipeline. **Does not run volunteer workers** on the console machine.

```powershell
.\scripts\serve_task_console.ps1
```

Open http://127.0.0.1:8765 — **Dispatch task** posts a goal via `create_task`; **Watch goal** monitors trace on staging.

To execute work on your PC, start **`agentswarm-volunteer`** separately (same or another machine) with the right capabilities.

Local all-in-one dev (console machine runs workers): `.\scripts\start_task.ps1` — not the task console.

See [task-workflow.md](task-workflow.md).

### Preview the static pilot locally

Same layout as production static hosting (index, news-hub, dashboard):

```powershell
.\scripts\preview_pilot_site.ps1
```

```bash
./scripts/preview_pilot_site.sh
```

### Public pilot (theebie.de)

The static pilot is live at **https://theebie.de/sites/agentswarm/** (news-hub, dashboard). To redeploy after local changes:

```powershell
.\scripts\deploy_pilot_theebie.ps1
```

```bash
./scripts/deploy_pilot_theebie.sh
```

See [deploy.md](deploy.md). Optional GitHub Pages mirror for forks: `python scripts/check_pages_ready.py`.

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

### Unit and integration tests (matches CI)

```bash
python -m pytest -q platform/tests
python -m pytest -q agents/tests
python -m pytest -q packages/mcp-adapter/tests
python -m pytest -q pilot/news-hub/tests
```

Or all Python tests:

```bash
python -m pytest -q platform/tests agents/tests
```

### TypeScript SDK

```bash
cd packages/sdk-typescript
npm install
npm test
```

### Staging API smoke (theebie)

Production staging uses enforced registration. Fetch a bootstrap token from the server (maintainer) or set `AGENTSWARM_BOOTSTRAP_TOKEN`:

```powershell
$env:AGENTSWARM_BOOTSTRAP_TOKEN = (ssh root@theebie.de "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' /etc/agentswarm/platform.env | cut -d= -f2-").Trim()
$env:AGENTSWARM_EXPECT_DISPATCH = "1"
$env:AGENTSWARM_VERIFY_QUICK = "1"
python scripts/verify_production_staging.py https://theebie.de/agentswarm/api
```

Full maintainer bundle (SSH-fetches secrets, includes appeal/lease-reclaim/MCP; subjective demo needs local prep):

```bash
bash scripts/run_full_staging_verify.sh
```

See [production-hardening.md](production-hardening.md) and [development.md](development.md#testing).

## Environment variables

| Variable | Default | When to set |
|----------|---------|-------------|
| `AGENTSWARM_PLATFORM_URL` | `http://127.0.0.1:8000` | Platform not on localhost:8000 — **public:** `https://theebie.de/agentswarm/api` |
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
- [Quickstart: external agent](quickstart-external-agent.md) — dispatch mode on staging
- [Deploy guide](deploy.md) — theebie.de static site + VPS platform hosting
- [Production hardening](production-hardening.md) — staging verify bundle
- [Development guide](development.md) — contribute changes
