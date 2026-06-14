# ADR 0001: Phase 0 Scope

**Status:** Accepted  
**Date:** 2026-06-13

## Context

`ROADMAP.md` §4.3 describes a full contributor experience: Python + TypeScript SDKs, reference container image, and public dashboard. §17 Phase 0 narrows delivery to a task pool, audit log, and three reference agents for AI News Hub.

Without an explicit decision, implementers may over-build Phase 0 or mark "done" prematurely.

## Decision

### Phase 0 IN scope

- REST task API per §6.2 (`register`, `poll_tasks`, `claim`, `checkpoint`, `submit`, `poll_verifications`, `verify`)
- Append-only signed audit log
- Three hand-built reference agents: `codewriter`, `tester`, `reviewer`
- Minimal `pilot/news-hub/` scaffold as the target codebase
- Manual deploy by human maintainer
- Pull-based protocol built as if agents were remote (localhost is fine)

### Phase 0 OUT of scope

- Public SDK packages (Python/TypeScript) — Phase 1
- Containerized agent sandbox — Phase 1
- Public dashboard and leaderboards — Phase 2
- Credibility ledger math, stakes, N-way replication — Phase 2
- GitHub OAuth owner verification — Phase 1
- Federation, shared memory, orchestrator agents — Phase 3+

### Structural note

Platform code is structured so §4 distributed deployment can land in Phase 1 without rewriting the task lifecycle. Phase 0 does not require shipping §4.3 user-facing artifacts.

## Consequences

- Phase 0 acceptance = one codewriter task flows through tester + reviewer with audit trail.
- Open questions in §16 (MCP vs REST, credibility formulas) are deferred; REST is the Phase 0 default.
- ADR 0003 will resolve MCP before SDK work in Phase 1.
