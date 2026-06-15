# Execution Plan

**Living development roadmap** for AgentSwarm. This is the canonical *how we build it* document.

| Document | Role |
|----------|------|
| [ROADMAP.md](../ROADMAP.md) | Product vision and long-term spec |
| **This file** | Ordered work packages, acceptance criteria, dependencies |
| [status.md](status.md) | Checkbox progress tracker |
| [adr/](adr/) | Locked architectural decisions |

**Last updated:** 2026-06-15

> **Phase 6+ (volunteer client & central dispatch):** see [ROADMAP_CHANGES.md](../ROADMAP_CHANGES.md) for the full design handoff and P6.0–P6.10 packages.

---

## How to use this plan

1. Pick the **first incomplete package** in the current phase.
2. Complete all steps; run verification commands.
3. Check acceptance criteria before marking done in [status.md](status.md).
4. Open a PR; link the package ID (e.g. `P0.3`) in the description.
5. ADRs marked **required** must be merged before dependent packages start.

Packages are **sequential within a phase** unless marked parallel. Do not skip acceptance criteria.

---

## Phase 0 — Foundation (MVP)

**Goal:** Closed swarm of trusted agents producing the first AI News Hub version.

**Phase acceptance:** Codewriter → tester → reviewer loop works with audit trail; pilot is deployable; Phase 0 tagged.

| ID | Package | Status | Depends on |
|----|---------|--------|------------|
| P0 | Repository bootstrap | ✅ Done | — |
| P1 | Monorepo layout + ADR 0001 | ✅ Done | P0 |
| P2 | Task pool MVP + audit log | ✅ Done | P1, ADR 0004 |
| P3 | Reference agents | ✅ Done | P2 |
| P4 | AI News Hub scaffold | ✅ Done | P1 |
| P5 | CI + quality gates | ✅ Done | P2 |
| P6 | Documentation | ✅ Done | P0 |
| **P0.7** | **Deploy runbook + manual deploy** | ✅ Pilot on theebie.de (`/sites/agentswarm/`); Pages optional for forks | P2, P4 |
| P0.8 | Cross-platform demo script | ✅ Done | P3 |
| P0.9 | Phase 0 close-out tag | ✅ Done | P0.7 |

### P0.7 — Deploy runbook + manual deploy

| Field | Value |
|-------|--------|
| **Goal** | Platform and pilot runnable outside localhost |
| **In scope** | [deploy.md](deploy.md), env template, backup notes |
| **Out of scope** | Automated deploy agent, Kubernetes |
| **Steps** | 1. Document VM setup (uvicorn + systemd or equivalent). 2. Document static pilot hosting (theebie.de `/sites/agentswarm/` or nginx). 3. Document `AGENTSWARM_DB` backup. 4. Maintainer runs deploy once and records URL in status.md. |
| **Verification** | `curl https://<host>/health` returns ok; pilot URL loads |
| **Acceptance** | Another person can deploy from docs alone |
| **Human review** | Yes |

### P0.8 — Cross-platform demo script (optional)

| Field | Value |
|-------|--------|
| **Goal** | Parity with `scripts/demo_phase0.ps1` on macOS/Linux |
| **In scope** | `scripts/demo_phase0.sh` |
| **Verification** | `bash scripts/demo_phase0.sh` exits 0 on Linux/macOS |
| **Acceptance** | CI or maintainer confirms on non-Windows host |

### P0.9 — Phase 0 close-out

| Field | Value |
|-------|--------|
| **Goal** | Declare Phase 0 complete |
| **Steps** | 1. All P0.x acceptance met. 2. Update status.md. 3. Git tag `v0.1.0-phase0`. 4. Short release note in README or GitHub Release. |
| **Acceptance** | Tag exists; status.md Phase 0 items all checked |

---

## Phase 0.5 — Pilot depth (recommended before Phase 1)

**Goal:** AI News Hub has real structure so agents do meaningful work, not only marker inserts.

| ID | Package | Status | Depends on |
|----|---------|--------|------------|
| P0.5.1 | News item JSON schema + samples | ✅ Done | P4 |
| P0.5.2 | Render feed from JSON in pilot | ✅ Done | P0.5.1 |
| P0.5.3 | Task type `codewriter.add-article` | ✅ Done | P0.5.2, P3 |
| P0.5.4 | Maintainer enqueue script | ✅ Done | P0.5.3 |

### P0.5.1 — News item schema

| Field | Value |
|-------|--------|
| **In scope** | `pilot/news-hub/schema/news-item.json`, 3–5 sample items in `data/` |
| **Acceptance** | Schema validates samples; documented in [pilot-news-hub.md](pilot-news-hub.md) |

### P0.5.2 — Feed rendering

| Field | Value |
|-------|--------|
| **In scope** | `index.html` or small JS loads `data/articles.json` and renders list |
| **Acceptance** | `pytest` still passes; feed visible in browser |

### P0.5.3 — Add-article task type

| Field | Value |
|-------|--------|
| **In scope** | New task type; codewriter appends validated item to JSON; tester validates schema + tests |
| **Acceptance** | Demo enqueues add-article task; full verify loop completes |

### P0.5.4 — Maintainer enqueue script

| Field | Value |
|-------|--------|
| **In scope** | `scripts/enqueue_task.py` — create tasks from CLI |
| **Acceptance** | Human can enqueue work without curl |

---

## Phase 1 — Open Plugin API

**Goal:** External contributor registers an agent on their machine and picks up real tasks.

**Blockers before coding:** ADR 0002 (identity), ADR 0003 (MCP vs REST).

| ID | Package | Status | Depends on |
|----|---------|--------|------------|
| P1.0 | ADR 0002 — Identity model | ✅ Accepted | P0.9 |
| P1.1 | ADR 0003 — MCP vs REST spike | ✅ Accepted | P0.9 |
| P1.2 | Persistent agent key storage | ✅ Done | P1.0 |
| P1.3 | GitHub OAuth owner verification | ✅ Done | P1.0 |
| P1.4 | Hardened registration API | ✅ Done | P1.2, P1.3 |
| P1.5 | Task creation auth | ✅ Done | P1.4 |
| P1.6 | Capability schema + version signatures | ✅ Done | P1.4 |
| P1.7 | Python SDK (`packages/sdk-python/`) | ✅ Done | P1.1, P1.4 |
| P1.8 | TypeScript SDK | ✅ Done | P1.7, ADR 0003 |
| P1.9 | Quickstart doc + external machine test | ✅ Done | P1.7 |
| P1.10 | Resource budgets + egress allowlist (minimal) | ✅ Done | P1.4 |

### P1.0 — ADR 0002 (identity)

See [adr/0002-identity-model.md](adr/0002-identity-model.md). **Human review required.**

**Acceptance:** ADR status = Accepted; implementation packages unblocked.

### P1.1 — ADR 0003 (protocol)

Time-boxed spike (≤4 hours). See [adr/0003-protocol-rest-vs-mcp.md](adr/0003-protocol-rest-vs-mcp.md).

**Acceptance:** Recommendation: REST-first + MCP adapter, MCP-native, or hybrid — with rationale.

### P1.2 — Persistent agent keys

| Field | Value |
|-------|--------|
| **In scope** | Key file or env path; agents reuse identity across restarts |
| **Out of scope** | HSM, cloud KMS |
| **Acceptance** | Same `agent_id` after restart; documented in [agents.md](agents.md) |

### P1.3 — GitHub OAuth

| Field | Value |
|-------|--------|
| **In scope** | Owner links GitHub account; registration requires valid OAuth session or token |
| **Acceptance** | Second machine registers with verified owner; audit log records `owner_github_id` |

### P1.4 — Hardened registration

| Field | Value |
|-------|--------|
| **In scope** | Implement ADR 0002; signed registration payload; rate limits |
| **Verification** | Integration test: register → poll → claim on external host |
| **Acceptance** | Unauthenticated registration spam rejected |

### P1.5 — Task creation auth

| Field | Value |
|-------|--------|
| **In scope** | Only maintainer API keys or orchestrator agents can `POST /tasks` |
| **Acceptance** | Anonymous task creation returns 401/403 |

### P1.7 — Python SDK

| Field | Value |
|-------|--------|
| **In scope** | `packages/sdk-python/` — register, poll, claim, checkpoint, submit, sign |
| **Acceptance** | Quickstart works in <30 min on fresh machine per ROADMAP §17 Phase 1 |

### P1.9 — External machine quickstart

| Field | Value |
|-------|--------|
| **In scope** | `docs/quickstart-external-agent.md` |
| **Acceptance** | Maintainer reproduces on second machine; documented in README |

---

## Phase 2 — Credibility & Verification

**Do not start until Phase 1 acceptance met.**

| ID | Package | Status | Depends on |
|----|---------|--------|------------|
| P2.0 | `docs/credibility-spec.md` + simulations | ✅ Done | P1.9 |
| P2.1 | Credibility ledger storage + API hooks | ✅ Done | P2.0 |
| P2.2 | Stake-on-claim | ✅ Done | P2.1 |
| P2.3 | N-way replication (one task type) | ✅ Done | P2.1 |
| P2.4 | Canary injection | ✅ Done | P2.3 |
| P2.5 | Public dashboard (read-only) | ✅ Done | P2.1 |

**Gate:** P2.0 requires human review of math before P2.1 code.

---

## Phase 3 — Self-Orchestration & Shared Memory

| ID | Package | Status |
|----|---------|--------|
| P3.1 | Planner agent (minimal) | ✅ Done | P2.1 |
| P3.2 | Orchestrator agent (gap detection) | ✅ Done | P3.1, P3.3 |
| P3.3 | Shared memory store (read-all, gated write) | ✅ Done | P2.1 |
| P3.4 | Moderator automation | ✅ Done | P3.2 |

Detail when Phase 2 is underway. See [ROADMAP.md §17](../ROADMAP.md#17-phases--milestones).

---

## Phase 4 — Federation

| ID | Package | Status |
|----|---------|--------|
| P4.1 | Multi-project task pool | ✅ Done |
| P4.2 | Per-project credibility | ✅ Done |
| P4.3 | Cross-project reputation rules | ✅ Done |
| P4.4 | Governance templates | ✅ Done |

Deferred until Phase 3 demonstrates single-project self-orchestration.

---

## Beyond Phase 4 — what to build next

Phases **0–4 are implemented in code** (see [status.md](status.md)). [ROADMAP.md](../ROADMAP.md) does not define a formal Phase 5; the items below are the **recommended next packages**, ordered by impact.

| Priority | Package | Goal | ROADMAP anchor |
|----------|---------|------|----------------|
| **P5.0** | **Production platform on VPS** | Public `GET /health`, systemd, TLS, backups — agents point at a real URL | §4.3, P0.7 remainder |
| **P5.1** | **Live swarm on production** | Planner/orchestrator/moderator/deployer running against public API + theebie deploy hook | §3 Phase 3 acceptance |
| **P5.2** | **Pilot product depth** | Scraper/summarizer/classifier agents; news hub fed by real tasks, not only demos | §2, §5 content agents |
| **P5.3** | **External contributor trial** | One non-maintainer runs [quickstart-external-agent.md](quickstart-external-agent.md) against production | §17 Phase 1 acceptance |
| **P5.4** | **Credibility spec sign-off** | Human review of [credibility-spec.md](credibility-spec.md) parameters on staging | §9, §16 |
| **P5.5** | **MCP adapter** (optional) | `packages/mcp-adapter/` exposing §6.2 ops per [ADR 0003](adr/0003-protocol-rest-vs-mcp.md) | §6, ADR 0003 |
| **P5.6** | **Tournaments & bounties** | Parallel attempts + extra stake on hard tasks | §7.2, §7.3 |
| **P5.7** | **Agent versioning** | Enforce / surface `version_signature` bumps in registry | §14 |
| **P5.8** | **Production staging verify** | Post-deploy verification bundle for public API | deploy.md §7 |
| **P5.9** | **Major-version probation** | Low-tier-only claims until N verified accepts after major bump | §14 |
| **P5.10** | **Version downgrade rejection** | Block same-family version_signature downgrades on reconnect | §14 |
| **P5.11** | **Registration auth hardening** | Expose auth posture; verify scripts support enforced registration | Phase 1 |

**Not blocking:** GitHub Pages mirror for forks ([deploy.md](deploy.md) Option B). Operator auth enable: [production-hardening.md](production-hardening.md).

### P5.0 — Production platform (highest leverage)

| Field | Value |
|-------|--------|
| **Goal** | `AGENTSWARM_PLATFORM_URL=https://…` reachable over HTTPS |
| **In scope** | VPS + systemd + reverse proxy on theebie.de (subdomain) or separate host; [deploy.md](deploy.md) §1 |
| **Out of scope** | Kubernetes, multi-region |
| **Verification** | `curl https://<api-host>/health`; external agent quickstart against prod |
| **Acceptance** | Deploy checklist §7 in deploy.md all checked except optional Pages |

### P5.1 — Autonomous swarm on production

| Field | Value |
|-------|--------|
| **Goal** | Swarm runs without manual demo scripts |
| **In scope** | Long-running planner/orchestrator/moderator/deployer processes; `AGENTSWARM_DEPLOY_HOOK=./scripts/deploy_pilot_theebie.sh` |
| **Acceptance** | New article task enqueued → verified → optional deploy sign-off path exercised weekly |

### P5.2 — News hub as a product

| Field | Value |
|-------|--------|
| **Goal** | [pilot/news-hub/](pilot/news-hub/) updated by agent tasks, visible on [theebie.de/sites/agentswarm/](https://theebie.de/sites/agentswarm/) |
| **In scope** | `scraper`, `summarizer`, or `classifier` reference agents; enqueue scripts |
| **Acceptance** | Maintainer does not hand-edit `articles.json` for a week |

### P5.3 — External contributor trial

| Field | Value |
|-------|--------|
| **Goal** | A non-maintainer machine runs [quickstart-external-agent.md](quickstart-external-agent.md) against production |
| **In scope** | `scripts/verify_external_contributor.py`, demo wrappers, quickstart production section |
| **Verification** | `python scripts/verify_external_contributor.py` against `https://theebie.de/agentswarm/api` |
| **Acceptance** | Isolated identity dir → register → same `agent_id` on reconnect → poll OK → optional enqueue + `codewriter --once` → task `submitted` or `verified` |

### P5.4 — Credibility spec sign-off

| Field | Value |
|-------|--------|
| **Goal** | Human-reviewed credibility parameters enabled on staging |
| **In scope** | `GET /platform/config` credibility block, `credibility-pilot-params.json`, `verify_credibility_staging.py` |
| **Verification** | `python scripts/verify_credibility_staging.py` |
| **Acceptance** | Platform `credibility.enabled=true`, params match pilot file, new agent seeds at `initial_score`, simulation tests pass |

### P5.5 — MCP adapter (optional)

| Field | Value |
|-------|--------|
| **Goal** | MCP-native clients can drive the §6.2 pull protocol via tools |
| **In scope** | `packages/mcp-adapter/` (`agentswarm-mcp` stdio server), `verify_mcp_adapter.py` |
| **Verification** | `python scripts/verify_mcp_adapter.py` |
| **Acceptance** | Eight ADR-mapped tools registered; optional live `/health` smoke |

### P5.6 — Tournaments & bounties

| Field | Value |
|-------|--------|
| **Goal** | Parallel attempts with loser consolation; extra credibility on valuable tasks |
| **In scope** | `payload.tournament`, `payload.bounty`, credibility hooks, `verify_tournaments_bounties.py` |
| **Verification** | `python scripts/verify_tournaments_bounties.py` |
| **Acceptance** | Tournament quorum → winners mint accept, losers mint good_attempt; bounty adds mint on verify |

### P5.7 — Agent versioning

| Field | Value |
|-------|--------|
| **Goal** | Enforce and surface `version_signature` bumps in the registry |
| **In scope** | `agent_versioning.py`, `GET /agents/{id}/versions`, major-bump credibility haircut |
| **Verification** | `python scripts/verify_agent_versioning.py` |
| **Acceptance** | Format enforced; history records initial/minor/major; major bump applies `version.major_haircut` |

### P5.8 — Production staging verification

| Field | Value |
|-------|--------|
| **Goal** | One-command post-deploy verification for the public staging API |
| **In scope** | `verify_production_staging.py`, `verify_agent_versioning_staging.py`, [production-hardening.md](production-hardening.md) |
| **Verification** | `AGENTSWARM_EXPECT_DISPATCH=1 python scripts/verify_production_staging.py` |
| **Acceptance** | Quick bundle passes after deploy; full bundle documented for pre-release |

### P5.9 — Major-version probation

| Field | Value |
|-------|--------|
| **Goal** | Extra verification gate after major `version_signature` bumps (ROADMAP §14) |
| **In scope** | `version_probation.py`, claim tier cap during probation, profile + config exposure |
| **Verification** | `python -m pytest platform/tests/test_version_probation.py -q` |
| **Acceptance** | Major bump sets probation counter; medium/high claims blocked until N verified accepts |

### P5.10 — Version downgrade rejection

| Field | Value |
|-------|--------|
| **Goal** | Prevent owners from rolling back `version_signature` on an existing agent identity |
| **In scope** | `is_version_downgrade`, `assert_version_reconnect_allowed`, `AGENTSWARM_VERSION_REJECT_DOWNGRADES` |
| **Verification** | `python -m pytest platform/tests/test_agent_versioning.py -q` |
| **Acceptance** | Same-family downgrades return 400; opt-out via env; family change still allowed |

### P5.11 — Registration auth hardening

| Field | Value |
|-------|--------|
| **Goal** | Surface registration auth posture and keep verify scripts working when auth is enforced |
| **In scope** | `auth` block on `GET /platform/config`, bootstrap-aware verify scripts, `verify_registration_auth.py` |
| **Verification** | `python scripts/verify_registration_auth.py` |
| **Acceptance** | Config exposes `auth.enforced`; anonymous register returns 401 when enforced; deploy verify uses bootstrap |

### P6.11 — Phase 6 close-out

| Field | Value |
|-------|--------|
| **Goal** | Ship dispatch staging verify + document Phase 6 completion |
| **In scope** | `verify_dispatch_staging.py`, wire into `verify_production_staging.py`, status/README updates, tag `v0.7.0-phase6` |
| **Verification** | `python scripts/verify_dispatch_staging.py` · `python -m pytest platform/tests -q` |
| **Acceptance** | Staging dispatch smoke passes; docs record close-out tag |

### P7.0 — Assignment long-poll

| Field | Value |
|-------|--------|
| **Goal** | Server-side long-poll for dispatch assignments (ROADMAP_CHANGES open Q1) |
| **In scope** | `wait_sec` on `/assignments/pending`, `/assignments/wait`, `assignment_wait.py`, ADR 0006, `DispatchClient` uses server long-poll |
| **Verification** | `python -m pytest platform/tests/test_assignment_long_poll.py -q` |
| **Acceptance** | Clients wait in one HTTP request; config exposes `dispatch.long_poll_max_sec`; pull mode unchanged |

### P7.1 — Credit pricing per task class

| Field | Value |
|-------|--------|
| **Goal** | Tunable credit burn/mint table per task class (ROADMAP_CHANGES economics) |
| **In scope** | `credit_pricing.py`, `credits.pricing` on `/platform/config`, `difficulty` on creative goals, env/JSON overrides |
| **Verification** | `python -m pytest platform/tests/test_credit_pricing.py -q` |
| **Acceptance** | Goal post burns `post_cost * difficulty`; reviewer mint uses class table; defaults match prior behavior |

### P7.2 — Volunteer model allowlist

| Field | Value |
|-------|--------|
| **Goal** | Curated LLM allowlist published by platform and enforced in volunteer client (ADR 0007) |
| **In scope** | `model_allowlist.py` + JSON on platform, `models` on config, presence guard, client cross-check |
| **Verification** | `python -m pytest platform/tests/test_platform_model_allowlist.py agents/tests/test_model_allowlist.py -q` |
| **Acceptance** | Client and platform JSON match; unknown `model_id` rejected when enforce flag set |

### P7.3 — Human appeal for subjective rejects

| Field | Value |
|-------|--------|
| **Goal** | Poster can appeal rejected creative goals; maintainer upholds or overturns (ADR 0008) |
| **In scope** | `creative_goal_appeals` table, appeal + resolve endpoints, credit refund on overturn |
| **Verification** | `python -m pytest platform/tests/test_creative_appeal.py -q` |
| **Acceptance** | Rejected goal → appeal pending → overturn sets verified + refunds poster |

### P7.4 — Full staging verify bundle

| Field | Value |
|-------|--------|
| **Goal** | One-command full pre-release verify against theebie, including P7 unit + live checks |
| **In scope** | Extend `verify_production_staging.py` full mode (P7 pytest bundle, `verify_creative_appeal_staging.py`), `run_full_staging_verify.sh` / `.ps1`, optional `verify-staging-full.yml`, fix external contributor codewriter auth under enforced registration |
| **Verification** | `bash scripts/run_full_staging_verify.sh` (or `.ps1`) · `python -m pytest platform/tests/test_verify_production_staging_full.py -q` |
| **Acceptance** | Full bundle passes on theebie with bootstrap token; news/MCP skippable via env when swarm idle |

### P7.5 — Ollama runtime executor

| Field | Value |
|-------|--------|
| **Goal** | Volunteer client can run subjective capsules via local Ollama (ADR 0007 `ollama` runtime) |
| **In scope** | `ollama_executor.py`, wire `resolve_executor()` for `runtime=ollama`, `ollama_model` on allowlist entry |
| **Verification** | `python -m pytest agents/tests/test_ollama_executor.py agents/tests/test_volunteer_client.py -q` |
| **Acceptance** | `creative.text` and `reviewer.subjective` call localhost Ollama; remote endpoints rejected; coordinator still uses deterministic plan builder |

### P7.6 — Reviewer hardware / VRAM guidance

| Field | Value |
|-------|--------|
| **Goal** | Document minimum volunteer hardware for subjective reviewers (ROADMAP_CHANGES open Q3) |
| **In scope** | `docs/volunteer-hardware.md`, link from quickstart / ADR 0007 |
| **Verification** | Doc review; references model allowlist tiers |
| **Acceptance** | Clear VRAM/RAM guidance for reviewer vs creative roles |

### P7.11 — Phase 7 close-out

| Field | Value |
|-------|--------|
| **Goal** | Declare Phase 7 complete; keep staging healthy on a schedule |
| **In scope** | Weekly `verify-staging-full.yml` cron, `scripts/close_phase7.sh` / `.ps1`, tag `v0.8.0-phase7`, README/status updates |
| **Verification** | `bash scripts/close_phase7.sh` · `python -m pytest platform/tests agents/tests -q` |
| **Acceptance** | Tag exists; scheduled workflow documented in [production-hardening.md](production-hardening.md) |

---

## Current focus

```
✅ Phases 0–4 core complete (code + tests + demos)
✅ P0.7 static pilot live on theebie.de (/sites/agentswarm/)
✅ P6.0–P6.2 dispatch mode (presence, pool.need, assignments) — behind AGENTSWARM_ASSIGNMENT_MODE=dispatch
✅ P6.3  Subjective creative.text + reviewer quorum (`POST /creative/goals`, `GET /creative/goals/{id}`)
✅ P6.4  Credits ledger (`GET /agents/{id}/credits`, burn on goal post, mint on verify)
✅ P6.5  Dev dispatch client (`agents/.../dispatch_client.py`, `scripts/run_dispatch_client.py`)
✅ P6.6  Docker worker image (`docker/worker/Dockerfile`, `--docker` on dispatch client)
✅ P6.7  Coordinator decomposition (`pool_needs` + deferred reviewer needs from coordinator plan)
✅ P6.8  Volunteer client shell (`agentswarm-volunteer`, `scripts/build_volunteer_exe.ps1`)
✅ P6.9  Git-backed coder capsule (`PATCH /projects/{id}/repo`, `POST .../git/patches`)
✅ P6.10 Staging API on theebie.de → https://theebie.de/agentswarm/api (`scripts/deploy_platform_theebie.sh`)
✅ P5.0  Production platform (systemd, TLS, backups, external verify) → same URL
✅ P5.1 Live swarm on production (`agentswarm-swarm`, `deploy_swarm_theebie.sh`)
✅ P5.2 News hub product pipeline (`enqueue_news_feed.py`, content agents)
✅ P5.3 External contributor trial (`verify_external_contributor.py`)
✅ P5.4 Credibility spec sign-off (`verify_credibility_staging.py`)
✅ P5.5 MCP adapter (`packages/mcp-adapter/`, `agentswarm-mcp`)
✅ P5.6 Tournaments & bounties (`payload.tournament`, `payload.bounty`)
✅ P5.7 Agent versioning (`GET /agents/{id}/versions`, major haircut)
✅ P5.8 Production staging verify bundle (`verify_production_staging.py`)
✅ P5.9 Major-version probation (`version_probation.py`, low-tier-only during probation)
✅ P5.10 Version downgrade rejection (`AGENTSWARM_VERSION_REJECT_DOWNGRADES`)
✅ P5.11 Registration auth hardening (`auth` on `/platform/config`, `verify_registration_auth.py`)
✅ Phase 5 close-out tag `v0.6.0-phase5`
✅ GitHub Pages fork mirror — https://malicorx.github.io/ai_agentswarm/
✅ Staging registration auth enforced — [production-hardening.md](production-hardening.md)
✅ Phase 6 close-out — `verify_dispatch_staging.py`, tag `v0.7.0-phase6`
✅ P7.0 Assignment long-poll — `/assignments/wait`, ADR 0006
✅ P7.1 Credit pricing table — `credit_pricing.py`, `credits.pricing` on config
✅ P7.2 Volunteer model allowlist — ADR 0007, `models` on config
✅ P7.3 Human appeal for subjective rejects — ADR 0008
✅ P7.4 Full staging verify bundle — `run_full_staging_verify.sh`, P7 checks in full mode
✅ P7.5 Ollama runtime executor — `ollama_executor.py`, localhost-only endpoint guard
✅ P7.6 Reviewer hardware / VRAM guidance — `docs/volunteer-hardware.md`
✅ Phase 7 close-out — weekly staging verify cron, tag `v0.8.0-phase7`
✅ P8.0 Staging model allowlist enforcement — `models.enforced=true` on theebie
✅ P8.1 Forge-agnostic git — ADR 0009, `forge_type` metadata only in v1
✅ P8.2 Coordinator planning — ADR 0010, optional single-shot Ollama planner
✅ P8.3 Volunteer subjective demo — `demo_volunteer_subjective_staging.sh`
✅ Phase 8 close-out — `close_phase8.sh`, tag `v0.9.0-phase8`
✅ P9.0 Pending pool need redispatch — idle presence + submit idle retry dispatch
✅ P9.1 Reviewer VRAM hardware gates — `vram_gb` on presence, dispatcher filter
```

---

## Phase 9 — Dispatch reliability

**Goal:** Assign work when volunteers arrive after a pool need is created.

| ID | Package | Status | Depends on |
|----|---------|--------|------------|
| **P9.0** | Pending pool need redispatch | ✅ Done | P6.2, P8.3 |
| **P9.1** | Reviewer VRAM hardware gates | ✅ Done | P7.6, P8.0 |

### P9.1 — Reviewer VRAM hardware gates

| Field | Value |
|-------|--------|
| **Goal** | Enforce minimum self-reported VRAM for reviewer dispatch (ROADMAP_CHANGES open Q3 server-side) |
| **In scope** | `hardware_gates.py`, `vram_gb` on presence, dispatcher filter, staging verify + hardening |
| **Verification** | `python -m pytest platform/tests/test_hardware_gates.py -q` · `bash scripts/harden_staging_hardware_gates_theebie.sh` |
| **Acceptance** | `hardware.enforced=true` on theebie; low/missing `vram_gb` rejected; eligible reviewers still assign |

### P9.0 — Pending pool need redispatch

| Field | Value |
|-------|--------|
| **Goal** | Assign `pool_needs` stuck in `pending` when idle agents heartbeat or finish a task |
| **In scope** | `_redispatch_pending_pool_needs()` on idle presence + post-submit idle |
| **Verification** | `python -m pytest platform/tests/test_dispatch.py -q` |
| **Acceptance** | Pool need created before reviewer presence still assigns on next idle heartbeat |

---

## Phase 8 — Production volunteer hardening

**Goal:** Close remaining operational gaps before wider volunteer rollout.

| ID | Package | Status | Depends on |
|----|---------|--------|------------|
| **P8.0** | Staging model allowlist enforcement | ✅ Done | P7.2, ADR 0007 |
| **P8.1** | Forge-agnostic git (ADR 0009) | ✅ Done | P6.9 |
| **P8.2** | Coordinator planning (ADR 0010) | ✅ Done | P7.5, P6.7 |
| **P8.3** | Volunteer subjective staging demo | ✅ Done | P8.2, P6.3 |
| **P8.11** | Phase 8 close-out | ✅ Done | P8.3 |

### P8.11 — Phase 8 close-out

| Field | Value |
|-------|--------|
| **Goal** | Tag production-volunteer hardening milestone after live subjective path on theebie |
| **In scope** | `close_phase8.sh` / `.ps1`, status/README updates, tag `v0.9.0-phase8` |
| **Verification** | `bash scripts/close_phase8.sh` · `python -m pytest platform/tests agents/tests -q` |
| **Acceptance** | Dispatch smoke + volunteer subjective demo exit 0 on theebie |

### P8.0 — Staging model allowlist enforcement

| Field | Value |
|-------|--------|
| **Goal** | Enforce curated `model_id` on theebie staging platform (ADR 0007 production default) |
| **In scope** | `harden_platform_model_allowlist_theebie.sh`, `verify_model_allowlist_staging.py`, wire into staging bundle + deploy verify |
| **Verification** | `bash scripts/harden_staging_model_allowlist_theebie.sh` · `python -m pytest platform/tests/test_verify_model_allowlist_staging.py -q` |
| **Acceptance** | `models.enforced=true` on theebie; unknown model presence rejected; allowlisted model accepted |

### P8.1 — Forge-agnostic git (ADR 0009)

| Field | Value |
|-------|--------|
| **Goal** | Lock v1 git capsules as forge-agnostic; resolve ROADMAP_CHANGES open Q7 |
| **In scope** | ADR 0009, `forge_types.py`, tests for `github`/`gitlab` labels, ROADMAP_CHANGES close-out |
| **Verification** | `python -m pytest platform/tests/test_forge_types.py platform/tests/test_git_patch.py -q` |
| **Acceptance** | Execution is local `git` only; `forge_type` is metadata; GitHub/GitLab are labels not API dependencies |

### P8.2 — Coordinator planning (ADR 0010)

| Field | Value |
|-------|--------|
| **Goal** | Resolve coordinator LLM vs planner question; optional single-shot Ollama planner on client |
| **In scope** | ADR 0010, `coordinator_planner.py`, Ollama coordinator path + fallback, `coordinator` on `/platform/config` |
| **Verification** | `python -m pytest agents/tests/test_coordinator_planner.py agents/tests/test_ollama_coordinator.py platform/tests/test_coordinator_config.py -q` |
| **Acceptance** | Default deterministic; `AGENTSWARM_COORDINATOR_LLM=1` enables one-shot LLM plan validated before submit |

### P8.3 — Volunteer subjective staging demo

| Field | Value |
|-------|--------|
| **Goal** | One-command demo: post creative goal → volunteer clients → verified quorum on staging |
| **In scope** | `demo_volunteer_subjective.py`, `demo_volunteer_subjective_staging.sh` / `.ps1`, unit tests |
| **Verification** | `python -m pytest platform/tests/test_demo_volunteer_subjective.py -q` · `bash scripts/demo_volunteer_subjective_staging.sh` |
| **Acceptance** | Demo exits 0 on theebie with `llm-mock-v1`; optional `--ollama` when local Ollama is running |

---

## Package prompt templates

Copy into Cursor/Composer when starting a package:

### P0.7

```text
Implement Package P0.7 for AgentSwarm: complete docs/deploy.md with VM + static
pilot hosting instructions. Add .env.example for platform. Verify health endpoint
is documented. Update docs/status.md when deploy checklist items are done.
```

### P1.0

```text
Finalize ADR 0002 (docs/adr/0002-identity-model.md): resolve open questions,
set status to Accepted after review. Do not implement OAuth yet unless ADR is Accepted.
```

### P1.1

```text
Time-boxed spike (max 4h): compare REST (current) vs MCP for AgentSwarm §6.2 ops.
Update docs/adr/0003-protocol-rest-vs-mcp.md with recommendation and consequences.
```

---

## Related

- [status.md](status.md) — checkboxes
- [development.md](development.md) — how to implement
- [reviews/ROADMAP_20260603_153456.md](reviews/ROADMAP_20260603_153456.md) — original package review snapshot
