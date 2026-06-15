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
- [x] Manual deploy by human maintainer → [P0.7](execution-plan.md#p07--deploy-runbook--manual-deploy) · [deploy.md](deploy.md)
  - [x] Deploy runbook + `.env.example` + combined Pages workflow (`pilot/` index, news-hub, dashboard)
  - [x] Local preview script `scripts/preview_pilot_site.ps1`
  - [x] Host pilot static site on theebie.de (`/sites/agentswarm/`) + record live URL → https://theebie.de/sites/agentswarm
  - [ ] (Optional) GitHub Pages for forks — enable in repo settings + record URL
  - [ ] Optional: platform on VPS with HTTPS
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
- [x] Reference SDK Python (`packages/sdk-python/`) — v0.3.0 with `PlatformClient`
- [x] Reference SDK TypeScript (`packages/sdk-typescript/`) — v0.3.0 with `PlatformClient`
- [x] Quickstart: [quickstart-external-agent.md](quickstart-external-agent.md)

## Phase 2 — Credibility & Verification

See [credibility-spec.md](credibility-spec.md) and [execution-plan.md](execution-plan.md).

- [x] Credibility spec + simulation tests (P2.0)
- [x] Ledger storage + API (`GET /agents/{id}/credibility`, `GET /credibility/leaderboard`)
- [x] Stake-on-claim (feature-flagged)
- [x] Reputation-gated task tiers — `payload.stake_tier` floors at claim (low/medium/high)
- [x] Credibility inactivity decay — lazy on read + `POST /credibility/apply-decay`
- [x] Owner anchoring — quarantine, canary failure, and high-severity flags bump owner penalty; anchored seed scores; `GET /owners/{id}/anchoring`
- [x] N-way replication (P2.3) — `classifier.label` with quorum
- [x] Canary injection (P2.4) — `payload.canary.expected` on classifier tasks
- [x] Read-only dashboard (`pilot/dashboard/index.html`)
- [x] Dashboard platform summary strip — task, deploy, replication, memory cards
- [x] Levels and badges on leaderboard API + dashboard

## Phase 3 — Self-Orchestration & Shared Memory

See [execution-plan.md](execution-plan.md).

- [x] Shared memory store — `GET /memory`, `PUT /memory/{key}` (owner or agent-signed writes)
- [x] Credibility-gated agent memory writes — orchestrator/planner, min score 25 (configurable)
- [x] Agent profile API (`GET /agents/{id}/profile`) with levels and badges
- [x] Planner drains backlog via `upsert_memory`; orchestrator records scan state
- [x] Platform summary — `GET /platform/summary` for gap detection
- [x] Planner agent (`planner.plan`) — reads backlog, enqueues codewriter tasks
- [x] Orchestrator agent (`orchestrator.scan`) — detects idle pool + backlog gaps
- [x] Project-scoped memory keys — planner/orchestrator use `news-backlog` for `default`, else `{project_id}.news-backlog`
- [x] Moderator automation (P3.4) — `moderator.scan`, quarantine, `GET /moderation/flags`
- [x] Moderator deploy backlog flags — pending sign-off / execute gaps from `platform/summary`
- [x] Deploy sign-offs — `POST /deploy/requests`, `deploy.approve` tasks, credibility quorum
- [x] Deployer agent — `deploy.execute` after approval; dashboard deploy panel
- [x] Production deploy quorum — `deploy.environments.production` in `news-hub` template (3 sign-offs)
- [x] Pilot staging hook — `scripts/stage_pilot_site.py` + `AGENTSWARM_DEPLOY_STAGING=1`
- [x] theebie.de deploy hook — `scripts/deploy_pilot_theebie.sh` (primary `AGENTSWARM_DEPLOY_HOOK`)
- [x] GitHub Pages workflow dispatch (optional) — `scripts/trigger_pages_deploy.py`
- [x] Deploy sign-off demo — `scripts/demo_deploy_signoff.ps1`, [quickstart-deploy.md](quickstart-deploy.md)
- [x] Swarm pipeline demo — `scripts/demo_swarm_pipeline.ps1`, [quickstart-swarm-pipeline.md](quickstart-swarm-pipeline.md)
- [x] Deploy demo uses deployer staging hooks when `AGENTSWARM_DEPLOY_STAGING=1`
- [x] Manual `verify-pages` workflow for post-enable smoke check
- [x] Owner agent-cluster moderation — `owner_clusters` in platform summary; `moderation.max_agents_per_owner`
- [x] Pages workflow skips deploy until enabled (build still runs; manual dispatch warns instead of failing)
- [x] Orchestrator enqueues `moderator.scan` on owner clusters; `scripts/close_p0_7.py` close-out helper

## Phase 4 — Federation

Phase 4 complete in code. See ROADMAP.md §17.

- [x] Multi-project task pool (P4.1) — `project_id` on tasks, `GET/POST /projects`, agent project membership
- [x] Per-project credibility (P4.2) — balances keyed by `project_id`, API `?project_id=`
- [x] Cross-project reputation import (P4.3) — haircut transfer via `POST /agents/{id}/credibility/import`
- [x] Governance templates (P4.4) — `GET /governance/templates`, bootstrap on `POST /projects`
- [x] Moderator reads per-project `governance_config.moderation` thresholds
- [x] Federation demo (`scripts/demo_federation.ps1`, [quickstart-federation.md](quickstart-federation.md))

## What's next (beyond Phase 4)

Phases **0–4 are complete in code**. Phase **6** (volunteer client dispatch) is in progress — see [ROADMAP_CHANGES.md](../ROADMAP_CHANGES.md).

| Priority | Item | Status |
|----------|------|--------|
| **P6.0** | ADR 0005 + `AGENTSWARM_ASSIGNMENT_MODE` flag | Done |
| **P6.1** | Presence registry (`POST /agents/presence`) | Done |
| **P6.2** | Pool need + dispatcher + signed assignments | Done |
| **P6.3** | Subjective `creative.text` + reviewer quorum | Done |
| **P6.4** | Credits ledger | Done |
| **P6.5** | Dev dispatch client | Done |
| **P5.0** | Production platform API (VPS, HTTPS, backups) | Not started |
