# ADR 0010: Coordinator planning (deterministic default, optional single-shot LLM)

**Status:** Accepted  
**Date:** 2026-06-15  
**Spec:** [ROADMAP_CHANGES.md](../../ROADMAP_CHANGES.md) open question #4

## Context

Creative goals flow through `coordinator.decompose`: the assigned client emits a **plan** (`pool_needs` + `deferred_pool_needs`) that the platform validates and enqueues. Today the default plan is **deterministic** (`build_default_creative_goal_plan`). The open question was whether coordinators should use a **single LLM call** or a **multi-step planner**.

## Decision

| Mode | When | Behavior |
|------|------|----------|
| **Deterministic default** | Always available | `build_default_creative_goal_plan` — creative.text then N reviewer.subjective needs |
| **Optional single-shot LLM** | Client opt-in (`AGENTSWARM_COORDINATOR_LLM=1`) + Ollama runtime | One `/api/chat` call returns JSON plan; client validates shape before submit |
| **Multi-step planner** | Deferred | Not in v1 |

### Platform (authoritative validation)

1. Coordinator submits plan JSON on `coordinator.decompose` verify.
2. `validate_coordinator_plan()` enforces allowed task types and schema.
3. If `pool_needs` is missing, platform applies deterministic default (existing fallback in `complete_coordinator_decompose_submit`).

`GET /platform/config` → `coordinator` block documents allowed task types and that LLM planning is **client-optional**.

### Client

- **In-process / mock / Docker:** always deterministic (`capsule_executor`).
- **Ollama:** deterministic unless `AGENTSWARM_COORDINATOR_LLM=1`; on LLM parse/validation failure, fall back to deterministic plan before submit.

The LLM may adjust `min_reviewers` count in `deferred_pool_needs[].spec.count` but cannot introduce disallowed task types.

## Consequences

- Platform behavior unchanged for clients that do not set `AGENTSWARM_COORDINATOR_LLM`.
- Operators can run coordinators on low-VRAM machines with deterministic planning.
- Future multi-step planner would be a new ADR + new task type or coordinator mode flag.

## Related

- [ADR 0005](0005-volunteer-client-dispatch.md) — dispatch assignments
- [ADR 0007](0007-model-allowlist.md) — Ollama runtime
- `platform/src/agentswarm_platform/coordinator_plan.py` — schema validation
- `agents/src/agentswarm_agents/coordinator_planner.py` — client helpers
