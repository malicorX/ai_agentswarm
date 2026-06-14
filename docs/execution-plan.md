# Execution Plan

**Living development roadmap** for AgentSwarm. This is the canonical *how we build it* document.

| Document | Role |
|----------|------|
| [ROADMAP.md](../ROADMAP.md) | Product vision and long-term spec |
| **This file** | Ordered work packages, acceptance criteria, dependencies |
| [status.md](status.md) | Checkbox progress tracker |
| [adr/](adr/) | Locked architectural decisions |

**Last updated:** 2026-06-13

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
| **P0.7** | **Deploy runbook + manual deploy** | 🔲 Partial (Pages workflow ready; enable in Settings) | P2, P4 |
| P0.8 | Cross-platform demo script | ✅ Done | P3 |
| P0.9 | Phase 0 close-out tag | ✅ Done | P0.7 |

### P0.7 — Deploy runbook + manual deploy

| Field | Value |
|-------|--------|
| **Goal** | Platform and pilot runnable outside localhost |
| **In scope** | [deploy.md](deploy.md), env template, backup notes |
| **Out of scope** | Automated deploy agent, Kubernetes |
| **Steps** | 1. Document VM setup (uvicorn + systemd or equivalent). 2. Document static pilot hosting (GitHub Pages or nginx). 3. Document `AGENTSWARM_DB` backup. 4. Maintainer runs deploy once and records URL in status.md. |
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

## Current focus

```
✅ P0–P6 complete
✅ P0.5 pilot depth complete
✅ P0.8 demo_phase0.sh
✅ P1.6  Capability schema (`GET /capabilities`, register validation)
✅ P1.8  TypeScript SDK (`packages/sdk-typescript/`)
✅ P1.9  Quickstart external agent
✅ P0.9  Tag v0.1.0-phase0
✅ P1.10 Resource budgets + egress allowlist
✅ P2.0–P2.2 Credibility spec, ledger, stake-on-claim
✅ P2.5 Read-only credibility dashboard
✅ P2.3 N-way replication (`classifier.label`)
✅ P2.4 Canary injection
✅ P3.1–P3.4 Planner, orchestrator, shared memory, moderator
✅ P4.1–P4.4 Federation: projects, cred, import, governance templates
✅ Project-scoped planner/orchestrator memory keys
✅ Tag v0.4.0-phase4
✅ Federation demo + quickstart
✅ Reputation-gated stake tiers (claim floors for medium/high)
✅ Leaderboard levels and badges
✅ Credibility-gated agent memory writes
✅ Agent profile API and client memory helper
✅ Dashboard profile panel; planner/orchestrator memory writes
✅ Tag v0.5.0-phase5
✅ Credibility inactivity decay
✅ Owner anchoring (quarantine penalty + anchored seeds)
✅ Owner anchoring: canary failures and high-severity flags
✅ Deploy sign-offs with credibility-gated `deploy.approve` quorum
→  P0.7  Deploy (enable GitHub Pages in repo Settings, then re-run workflow)
```

**Recommended order for solo developer:**

1. **P0.7** — finish Phase 0 properly
2. **P1.0 + P1.1** — lock ADRs (1–2 days)
3. **P0.5.1–P0.5.4** — make pilot interesting while thinking about identity
4. **P1.2–P1.9** — open the platform

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
