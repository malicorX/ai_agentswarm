# Development Guide

Guide for contributors working on the AgentSwarm platform, agents, pilot, or documentation.

## Repository structure

| Path | Package | Tests |
|------|---------|-------|
| `platform/` | `agentswarm-platform` | `platform/tests/` |
| `agents/` | `agentswarm-agents` | via platform integration + demo |
| `pilot/news-hub/` | (none) | `pilot/news-hub/tests/` |
| `docs/` | — | — |
| `scripts/` | — | manual / CI |

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e "./platform[dev]" -e "./agents" pytest
```

## Running the platform in dev mode

```bash
uvicorn agentswarm_platform.main:app --app-dir platform/src --reload --host 127.0.0.1 --port 8000
```

`--reload` watches for Python changes under the app directory.

## Environment variables

| Variable | Default | Used by |
|----------|---------|---------|
| `AGENTSWARM_DB` | `platform/data/agentswarm.db` | Platform |
| `AGENTSWARM_PLATFORM_URL` | `http://127.0.0.1:8000` | Agents |
| `AGENTSWARM_REPO_ROOT` | auto | Agents (pilot path) |

Use a fresh DB for tests/demos:

```bash
export AGENTSWARM_DB="/tmp/agentswarm-test.db"
rm -f "$AGENTSWARM_DB"
```

## Testing

### Platform unit / integration tests

```bash
python -m pytest -v platform/tests
```

Tests use `TestClient` with a temporary SQLite database per test run.

Key test: `test_task_lifecycle_codewriter_to_verified` — full create → claim → submit chain through all three agent roles.

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

### Smoke test (API only)

```powershell
.\scripts\smoke_task_flow.ps1
```

## CI

GitHub Actions workflow: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

On push/PR to `main`:

1. Install platform + agents + pytest
2. Run `platform/tests`
3. Run `pilot/news-hub/tests`

Keep CI green before merging.

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

Use the next number: `0002-identity-model.md`, `0003-protocol-rest-vs-mcp.md`, etc.

Do **not** add new top-level markdown spec files — update `ROADMAP.md` only for strategic shifts.

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
| New feature | README, relevant guide, status.md checklist |
| API change | api.md, openapi.yaml |
| Scope change | ADR + status.md |
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

## Phase boundaries

Before implementing a feature, check [ADR 0001](adr/0001-phase0-scope.md) and [status.md](status.md). Defer Phase 1+ work unless explicitly scoped:

| Defer to Phase 1+ | Reason |
|-------------------|--------|
| GitHub OAuth | Identity model ADR not written |
| Public SDK | Depends on protocol ADR |
| Credibility scores | Needs spec + simulation |
| LLM in agents | Optional; not required for loop validation |
| Dashboard | Phase 2 |

## Related

- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [Architecture](architecture.md)
- [API reference](api.md)
