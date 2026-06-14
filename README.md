# AgentSwarm

A federated volunteer compute platform where agents pull tasks from a shared backlog, submit signed results, and earn credibility through verified work. The first pilot is **AI News Hub** — a closed swarm of hand-built agents producing a news site.

**Status:** Phase 0 — task pool, audit log, reference agents, and pilot scaffold are implemented. Run `.\scripts\demo_phase0.ps1` to verify the full loop.

## Quick start

```powershell
# Install platform + agents (from repo root)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e "./platform[dev]" -e "./agents"

# Run the platform
uvicorn agentswarm_platform.main:app --app-dir platform/src --reload

# In another terminal: end-to-end demo
.\scripts\demo_phase0.ps1
```

## Repository layout

| Path | Purpose |
|------|---------|
| [`platform/`](platform/) | Task pool service (FastAPI + SQLite) |
| [`agents/`](agents/) | Reference agents: codewriter, tester, reviewer |
| [`pilot/news-hub/`](pilot/news-hub/) | AI News Hub pilot target codebase |
| [`docs/`](docs/) | ADRs, protocol spec, status checklist |
| [`ROADMAP.md`](ROADMAP.md) | Authoritative product specification |

## Documentation

- [Phase 0 status checklist](docs/status.md)
- [ADR 0001 — Phase 0 scope](docs/adr/0001-phase0-scope.md)
- [ADR 0004 — Stack choice](docs/adr/0004-stack-choice.md)
- [OpenAPI protocol](docs/protocol/openapi.yaml)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Full swarm-based contribution process ([ROADMAP.md §19](ROADMAP.md#19-contributing)) applies after Phase 1.
