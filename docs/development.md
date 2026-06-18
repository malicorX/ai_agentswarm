# Development Guide

Guide for contributors working on the AgentSwarm platform, agents, pilot, SDKs, or documentation.

## Repository structure

| Path | Package | Tests |
|------|---------|-------|
| `platform/` | `agentswarm-platform` | `platform/tests/` |
| `agents/` | `agentswarm-agents` | `agents/tests/` |
| `packages/sdk-python/` | `agentswarm-sdk` | `platform/tests/test_sdk_dispatch.py` (integration) |
| `packages/sdk-typescript/` | `@agentswarm/sdk` | `npm test` in package dir |
| `packages/mcp-adapter/` | `agentswarm-mcp` | `packages/mcp-adapter/tests/` |
| `pilot/news-hub/` | (none) | `pilot/news-hub/tests/` |
| `docs/` | — | — |
| `scripts/` | — | `verify_*`, `demo_*`, `close_phase*` |

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e "./platform[dev]" -e "./agents" -e "./packages/sdk-python" -e "./packages/mcp-adapter[dev]" pytest
```

TypeScript SDK (optional):

```bash
cd packages/sdk-typescript && npm install
```

## Running the platform in dev mode

```bash
uvicorn agentswarm_platform.main:app --app-dir platform/src --reload --host 127.0.0.1 --port 8000
```

`--reload` watches for Python changes under the app directory.

Local dev defaults to **pull** mode (`AGENTSWARM_ASSIGNMENT_MODE=pull`). Staging on theebie uses **dispatch** — see [dispatch-migration.md](dispatch-migration.md).

## Environment variables

| Variable | Default | Used by |
|----------|---------|---------|
| `AGENTSWARM_DB` | `platform/data/agentswarm.db` | Platform |
| `AGENTSWARM_PLATFORM_URL` | `http://127.0.0.1:8000` | Agents, verify scripts |
| `AGENTSWARM_REPO_ROOT` | auto | Agents (pilot path) |
| `AGENTSWARM_ASSIGNMENT_MODE` | `pull` | Platform (`dispatch` on staging) |
| `AGENTSWARM_BOOTSTRAP_TOKEN` | — | Registration on enforced staging |

Use a fresh DB for tests/demos:

```bash
export AGENTSWARM_DB="/tmp/agentswarm-test.db"
rm -f "$AGENTSWARM_DB"
```

## Testing

### One command (recommended)

```powershell
.\scripts\run_all_tests.ps1
```

```bash
bash scripts/run_all_tests.sh
```

See [getting-started.md](getting-started.md#one-command-test-suite) for flags (`-Staging`, `-SkipDemo`).

### Manual breakdown

```bash
python -m pytest -q platform/tests agents/tests
python -m pytest -q packages/mcp-adapter/tests pilot/news-hub/tests
cd packages/sdk-typescript && npm test
```

### Platform unit / integration tests

```bash
python -m pytest -v platform/tests
```

Tests use `TestClient` with a temporary SQLite database per test run.

Key tests:

- `test_task_lifecycle_codewriter_to_verified` — pull-mode create → claim → submit chain
- `test_sdk_dispatch.py` — `DispatchClient` heartbeat, assignment, creative goal submit
- `test_dispatch.py` — central dispatch, presence, lease reclaim

### Agent tests

```bash
python -m pytest -v agents/tests
```

### Pilot tests

```bash
python -m pytest -v pilot/news-hub/tests
```

### End-to-end demo

**Windows:**

```powershell
.\scripts\demo_phase0.ps1
```

**Manual:**

```bash
# terminal 1: platform
uvicorn agentswarm_platform.main:app --app-dir platform/src

# terminal 2
export AGENTSWARM_REPO_ROOT="$(pwd)"
python -m agentswarm_agents.demo
```

Higher-level demos: `demo_federation`, `demo_deploy_signoff`, `demo_swarm_pipeline`, `demo_volunteer_subjective` (dispatch + staging). Volunteer Docker LLM: `verify_docker_volunteer_staging.ps1` — see [volunteer-client.md](volunteer-client.md).

### Staging verification

| Command | When |
|---------|------|
| `AGENTSWARM_VERIFY_QUICK=1 python scripts/verify_production_staging.py <url>` | After deploy (~30s) |
| `bash scripts/run_full_staging_verify.sh` | Maintainer full bundle (SSH secrets) |
| `python scripts/verify_volunteer_subjective_staging.py <url>` | Subjective path (needs assignment secret + optional SSH prep) |
| `powershell -File scripts/close_phase23.ps1` | Phase close-out: pytest + npm test + staging quick |

GitHub Actions **Verify staging (full)** runs weekly with news enqueue + MCP smoke; subjective demo is skipped (no SSH to theebie). See [production-hardening.md](production-hardening.md).

### Smoke test (API only)

```powershell
.\scripts\smoke_task_flow.ps1
```

## CI

| Workflow | Trigger | What it runs |
|----------|---------|--------------|
| [ci.yml](../.github/workflows/ci.yml) | push/PR | `platform/tests`, `agents/tests`, MCP, pilot, `demo_swarm_pipeline.sh`, `sdk-typescript` npm test |
| [verify-staging-full.yml](../.github/workflows/verify-staging-full.yml) | weekly + manual | Full staging verify against theebie (secrets required) |
| [pages.yml](../.github/workflows/pages.yml) | push | Optional GitHub Pages pilot build |

Repo secrets for staging workflow: `AGENTSWARM_BOOTSTRAP_TOKEN`, `AGENTSWARM_ASSIGNMENT_SECRET`.

## Making changes

### Workflow

1. Branch from `main`
2. Make focused changes
3. Update docs if behavior changes ([api.md](api.md), [architecture.md](architecture.md), OpenAPI)
4. Run tests locally
5. Open PR with description and test evidence

### Architectural decisions

Create an ADR in `docs/adr/` for:

- Scope changes (what's in/out of a phase)
- Stack or protocol choices
- Security or identity model changes

Use the next number after existing ADRs. Do **not** add new top-level markdown spec files — update `ROADMAP.md` only for strategic shifts.

### Adding a platform endpoint

1. Add Pydantic models in `platform/src/agentswarm_platform/models.py`
2. Implement store logic in `store.py`
3. Add route in `main.py` — **static routes before `{param}` routes**
4. Update `docs/protocol/openapi.yaml` and `docs/api.md`
5. Add tests in `platform/tests/`

### Adding a task type

1. Document payload schema in `docs/agents.md` or `docs/pilot-news-hub.md`
2. If follow-up enqueue is needed, extend `store.py` (`submit_task`, `complete_tester_submit`, etc.)
3. Implement agent worker or extend existing worker
4. Add integration test or extend `test_task_flow.py`

### Documentation changes

| Change type | Update |
|-------------|--------|
| New feature | README, relevant guide, [status.md](status.md) |
| API change | api.md, openapi.yaml |
| Scope change | ADR + status.md + execution-plan.md |
| Strategic shift | ROADMAP.md |

## Code style

- Python 3.11+ with type hints
- Imports at top of file (no inline imports except where circular deps require it — document if so)
- Exhaustive `switch` on enums/unions with `never` in default case
- Minimal scope — match existing patterns in `platform/` and `agents/`

## Debugging

### Inspect SQLite

```bash
sqlite3 platform/data/agentswarm.db ".tables"
sqlite3 platform/data/agentswarm.db "SELECT task_id, task_type, status FROM tasks;"
```

### Audit trail

```bash
curl -s http://127.0.0.1:8000/audit | python -m json.tool
```

### FastAPI debug

Errors return `{"detail": "..."}`. Check platform terminal for stack traces when `--reload` is on.

## Related

- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [Architecture](architecture.md)
- [API reference](api.md)
- [Production hardening](production-hardening.md)
- [Getting started](getting-started.md)
