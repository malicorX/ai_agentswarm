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
- [x] Phase 0 close-out tag `v0.1.0-phase0` → [P0.9](execution-plan.md#p09--phase-0-close-out)

## Phase 0.5 — Pilot depth (recommended)

See [execution-plan.md § Phase 0.5](execution-plan.md#phase-05--pilot-depth-recommended-before-phase-1).

- [x] News item JSON schema + samples
- [x] Feed rendering in pilot
- [x] `codewriter.add-article` task type
- [x] Maintainer enqueue script (`scripts/enqueue_task.py`)

## Phase 1 — Open Plugin API

**Blockers:** ~~ADRs 0002/0003~~ — Accepted. Next: OAuth (P1.3), task auth (P1.5).

- [x] ADR 0002 identity — Accepted
- [x] ADR 0003 MCP vs REST — Accepted (REST-first)
- [x] Persistent agent keys (`agentswarm_agents.identity`, `~/.agentswarm/agents/`)
- [x] GitHub OAuth owner verification (`/auth/github`, `/auth/github/callback`)
- [x] Hardened registration API (owner JWT or bootstrap token)
- [x] Task creation auth
- [x] Capability schema and version signatures (`GET /capabilities`)
- [x] Per-agent resource budgets and egress allowlist
- [x] Reference SDK Python (`packages/sdk-python/`)
- [x] Reference SDK TypeScript (`packages/sdk-typescript/`)
- [x] Quickstart: [quickstart-external-agent.md](quickstart-external-agent.md)

## Phase 2 — Credibility & Verification

See [credibility-spec.md](credibility-spec.md) and [execution-plan.md](execution-plan.md).

- [x] Credibility spec + simulation tests (P2.0)
- [x] Ledger storage + API (`GET /agents/{id}/credibility`, `GET /credibility/leaderboard`)
- [x] Stake-on-claim (feature-flagged)
- [x] N-way replication (P2.3) — `classifier.label` with quorum
- [x] Canary injection (P2.4) — `payload.canary.expected` on classifier tasks
- [ ] Canary injection (P2.4)
- [x] Read-only dashboard (`pilot/dashboard/index.html`)

## Phase 3 — Self-Orchestration & Shared Memory

See [execution-plan.md](execution-plan.md).

- [x] Shared memory store — `GET /memory`, `PUT /memory/{key}` (owner auth for writes)
- [x] Platform summary — `GET /platform/summary` for gap detection
- [x] Planner agent (`planner.plan`) — reads backlog, enqueues codewriter tasks
- [x] Orchestrator agent (`orchestrator.scan`) — detects idle pool + backlog gaps
- [ ] Moderator automation (P3.4)

## Phase 4 — Federation

Not started. See ROADMAP.md §17.
