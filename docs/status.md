# AgentSwarm — Phase Status

Living checklist derived from [ROADMAP.md §17](../ROADMAP.md#17-phases--milestones).

## Phase 0 — Foundation (MVP)

Goal: closed swarm of trusted agents producing the first AI News Hub version.

**Guides:** [getting-started.md](getting-started.md) · [architecture.md](architecture.md) · [agents.md](agents.md)

- [x] Repository scaffolding (git, README, CONTRIBUTING, LICENSE)
- [x] Monorepo layout (`platform/`, `agents/`, `pilot/news-hub/`)
- [x] Phase 0 scope ADR ([0001](adr/0001-phase0-scope.md))
- [x] Task pool service (`create` / `claim` / `submit` / `verify`)
- [x] Append-only signed audit log
- [x] Three reference agents (`codewriter`, `tester`, `reviewer`)
- [x] Pull-based protocol skeleton (REST, localhost)
- [x] AI News Hub pilot scaffold
- [ ] Manual deploy by human maintainer
- [x] CI workflow (lint + tests)

## Phase 1 — Open Plugin API

- [ ] Agent registration (Ed25519 + GitHub owner verification)
- [ ] Public plugin API (HTTPS + long-polling)
- [ ] Capability schema and version signatures
- [ ] Per-agent resource budgets and egress allowlist
- [ ] Reference SDK (Python + TypeScript)
- [ ] Quickstart: "Bring your own summarizer in under 30 minutes"
- [ ] ADR: MCP vs REST ([0003](adr/0003-protocol-rest-vs-mcp.md) — pending)

## Phase 2 — Credibility & Verification

Not started. See ROADMAP.md §17.

## Phase 3 — Self-Orchestration & Shared Memory

Not started. See ROADMAP.md §17.

## Phase 4 — Federation

Not started. See ROADMAP.md §17.
