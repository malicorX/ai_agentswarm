# AgentSwarm — Phase Status

Living checklist derived from [ROADMAP.md §17](../ROADMAP.md#17-phases--milestones).

**Execution roadmap:** [execution-plan.md](execution-plan.md) — ordered packages and acceptance criteria.

## Phase 0 — Foundation (MVP)

Goal: closed swarm of trusted agents producing the first AI News Hub version.

**Guides:** [getting-started.md](getting-started.md) · [architecture.md](architecture.md) · [agents.md](agents.md) · [deploy.md](deploy.md)

- [x] Repository scaffolding (git, README, CONTRIBUTING, LICENSE)
- [x] Monorepo layout (`platform/`, `agents/`, `pilot/news-hub/`)
- [x] Phase 0 scope ADR ([0001](adr/0001-phase0-scope.md))
- [x] Task pool service (`create` / `claim` / `submit` / `verify`)
- [x] Append-only signed audit log
- [x] Three reference agents (`codewriter`, `tester`, `reviewer`)
- [x] Pull-based protocol skeleton (REST, localhost)
- [x] AI News Hub pilot scaffold
- [ ] Manual deploy by human maintainer → [P0.7](execution-plan.md#p07--deploy-runbook--manual-deploy) · [deploy.md](deploy.md)
- [x] CI workflow (lint + tests)
- [ ] Phase 0 close-out tag `v0.1.0-phase0` → [P0.9](execution-plan.md#p09--phase-0-close-out)

## Phase 0.5 — Pilot depth (recommended)

See [execution-plan.md § Phase 0.5](execution-plan.md#phase-05--pilot-depth-recommended-before-phase-1).

- [x] News item JSON schema + samples
- [x] Feed rendering in pilot
- [x] `codewriter.add-article` task type
- [x] Maintainer enqueue script (`scripts/enqueue_task.py`)

## Phase 1 — Open Plugin API

**Blockers:** Accept [ADR 0002](adr/0002-identity-model.md), complete [ADR 0003](adr/0003-protocol-rest-vs-mcp.md) spike.

- [ ] ADR 0002 identity — Proposed → Accepted
- [ ] ADR 0003 MCP vs REST — spike complete
- [ ] Persistent agent keys
- [ ] GitHub OAuth owner verification
- [ ] Hardened registration API
- [ ] Task creation auth
- [ ] Capability schema and version signatures
- [ ] Per-agent resource budgets and egress allowlist
- [ ] Reference SDK (Python + TypeScript)
- [ ] Quickstart: "Bring your own summarizer in under 30 minutes"

## Phase 2 — Credibility & Verification

Not started. See ROADMAP.md §17.

## Phase 3 — Self-Orchestration & Shared Memory

Not started. See ROADMAP.md §17.

## Phase 4 — Federation

Not started. See ROADMAP.md §17.
