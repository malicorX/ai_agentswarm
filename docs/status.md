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
  - [x] (Optional) GitHub Pages for forks — enable in repo settings + record URL → https://malicorx.github.io/ai_agentswarm
  - [x] Optional: platform on VPS with HTTPS → staging https://theebie.de/agentswarm/api
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

Phases **0–4 are complete in code**. Phase **6** (volunteer client dispatch) is **complete** — see [ROADMAP_CHANGES.md](../ROADMAP_CHANGES.md).

| Priority | Item | Status |
|----------|------|--------|
| **P6.0** | ADR 0005 + `AGENTSWARM_ASSIGNMENT_MODE` flag | Done |
| **P6.1** | Presence registry (`POST /agents/presence`) | Done |
| **P6.2** | Pool need + dispatcher + signed assignments | Done |
| **P6.3** | Subjective `creative.text` + reviewer quorum | Done |
| **P6.4** | Credits ledger | Done |
| **P6.5** | Dev dispatch client | Done |
| **P6.6** | Docker worker image | Done |
| **P6.7** | Coordinator decomposition | Done |
| **P6.8** | Production volunteer client (.exe) | Done |
| **P6.9** | Git-backed coder capsule | Done |
| **P6.10** | Staging API on theebie.de (`/agentswarm/api`) | Done → https://theebie.de/agentswarm/api |
| **P5.0** | Production platform API (VPS, HTTPS, backups) | Done → https://theebie.de/agentswarm/api |
| **P5.1** | Live swarm on production (`agentswarm-swarm`) | Done → https://theebie.de/agentswarm/api |
| **P5.2** | News hub product pipeline (scraper/summarizer/classifier) | Done → feed cron + `verify_news_pipeline.py` |
| **P5.3** | External contributor trial | Done → `verify_external_contributor.py` + quickstart production section |
| **P5.4** | Credibility spec sign-off | Done → `verify_credibility_staging.py` + pilot params on staging |
| **P5.5** | MCP adapter (optional) | Done → `packages/mcp-adapter/`, `agentswarm-mcp` |
| **P5.6** | Tournaments & bounties | Done → `payload.tournament`, `payload.bounty`, `verify_tournaments_bounties.py` |
| **P5.7** | Agent versioning | Done → `GET /agents/{id}/versions`, `verify_agent_versioning.py` |
| **P5.8** | Production staging verify | Done → `verify_production_staging.py`, [production-hardening.md](production-hardening.md) |
| **P5.9** | Major-version probation | Done → `version_probation.py`, `test_version_probation.py` |
| **P5.10** | Version downgrade rejection | Done → `AGENTSWARM_VERSION_REJECT_DOWNGRADES` |
| **P5.11** | Registration auth exposure | Done → `auth` on `/platform/config`, `verify_registration_auth.py` |
| **P6.11** | Phase 6 close-out | Done → `verify_dispatch_staging.py`, tag `v0.7.0-phase6` |
| **P7.0** | Assignment long-poll | Done → `/assignments/wait`, ADR 0006 |
| **P7.1** | Credit pricing per task class | Done → `credit_pricing.py`, `credits.pricing` on config |
| **P7.2** | Volunteer model allowlist | Done → ADR 0007, `models` on `/platform/config` |
| **P7.3** | Human appeal for subjective rejects | Done → ADR 0008, `/creative/goals/{id}/appeal` |
| **P7.4** | Full staging verify bundle | Done → `run_full_staging_verify.sh`, P7 checks in full mode |
| **P7.5** | Ollama runtime executor | Done → `ollama_executor.py`, `runtime=ollama` on volunteer client |
| **P7.6** | Reviewer hardware / VRAM guidance | Done → [volunteer-hardware.md](volunteer-hardware.md) |
| **P7.11** | Phase 7 close-out | Done → weekly `verify-staging-full.yml`, tag `v0.8.0-phase7` |
| **P8.0** | Staging model allowlist enforcement | Done → `models.enforced=true` on theebie (2026-06-15) |
| **P8.1** | Forge-agnostic git (ADR 0009) | Done → local `git` only; `forge_type` is metadata |
| **P8.2** | Coordinator planning (ADR 0010) | Done → deterministic default; optional Ollama single-shot |
| **P8.3** | Volunteer subjective staging demo | Done → `demo_volunteer_subjective.py` |
| **P8.11** | Phase 8 close-out | Done → `close_phase8.sh`, tag `v0.9.0-phase8` |
| **P9.0** | Pending pool need redispatch | Done → idle presence retries pending `pool_needs` |
| **P9.1** | Reviewer VRAM hardware gates | Done → `vram_gb` on presence + dispatch filter |
| **P9.2** | Weekly subjective demo in CI | Done → full verify + `verify-staging-full.yml` |
| **P9.11** | Phase 9 close-out | Done → `close_phase9.sh`, tag `v0.10.0-phase9` |
| **P10.0** | Expired assignment lease reclaim | Done → `reclaim_expired_assignment_leases()` |
| **P10.1** | Stale presence reclaim + subjective prep | Done → `maintain_dispatch_pool()`, prep scripts |
| **P10.2** | Isolated subjective verify | Done → `dispatch_include_owners`, `isolate_dispatch` |
| **P10.11** | Phase 10 close-out | Done → `close_phase10.sh`, tag `v0.11.0-phase10` |
| **P11.0** | Live lease reclaim verify | Done → `verify_lease_reclaim_staging.py`, pool reconcile |
| **P11.11** | Phase 11 close-out | Done → `close_phase11.sh`, tag `v0.12.0-phase11` |
| **P12.0** | Auto redispatch after reclaim | Done → agent-targeted redispatch, `prepare_pool_need_for_dispatch()` |
| **P12.11** | Phase 12 close-out | Done → `close_phase12.sh`, tag `v0.13.0-phase12` |
| **P13.0** | Scoped-only idle redispatch | Done → scoped idle redispatch + poll fallback |
| **P13.11** | Phase 13 close-out | Done → `close_phase13.sh`, tag `v0.14.0-phase13` |
| **P14.0** | Stale pending pool-need expiry | Done → `expire_stale_pending_pool_needs()`, prune scripts |
| **P14.11** | Phase 14 close-out | Done → `close_phase14.sh`, tag `v0.15.0-phase14` |

**Phase 14 close-out:** git tag [`v0.15.0-phase14`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.15.0-phase14) (2026-06-13).

**Phase 13 close-out:** git tag [`v0.14.0-phase13`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.14.0-phase13) (2026-06-15).

**Phase 12 close-out:** git tag [`v0.13.0-phase12`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.13.0-phase12) (2026-06-15).

**Phase 11 close-out:** git tag [`v0.12.0-phase11`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.12.0-phase11) (2026-06-15).

**Phase 10 close-out:** git tag [`v0.11.0-phase10`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.11.0-phase10) (2026-06-13).

**Staging model allowlist:** enforced 2026-06-15 via `scripts/harden_staging_model_allowlist_theebie.sh`.

**Phase 9 close-out:** git tag [`v0.10.0-phase9`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.10.0-phase9) (2026-06-13).

**Phase 8 close-out:** git tag [`v0.9.0-phase8`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.9.0-phase8) (2026-06-13).

**Phase 7 close-out:** git tag [`v0.8.0-phase7`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.8.0-phase7) (2026-06-15).

**Phase 6 close-out:** git tag [`v0.7.0-phase6`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.7.0-phase6) (2026-06-15).

**Phase 5 close-out:** git tag [`v0.6.0-phase5`](https://github.com/malicorX/ai_agentswarm/releases/tag/v0.6.0-phase5) (2026-06-15).

**GitHub Pages (fork mirror):** [https://malicorx.github.io/ai_agentswarm/](https://malicorx.github.io/ai_agentswarm/) — [deploy.md](deploy.md) Option B.

**Staging auth:** enabled 2026-06-15 (`auth.enforced=true` on theebie) via `scripts/harden_staging_auth_theebie.sh`.
