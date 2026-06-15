# ADR 0008: Human appeal for subjective creative goal rejects

**Status:** Accepted  
**Date:** 2026-06-15  
**Spec:** [ROADMAP_CHANGES.md](../../ROADMAP_CHANGES.md) open question #5

## Context

Subjective `creative.text` goals resolve via reviewer quorum. A reject is final for automation but posters need a **human escalation** path when they believe the jury misapplied the rubric.

## Decision

1. **File appeal** — `POST /creative/goals/{goal_id}/appeal` when goal `status=rejected`.
   - Only `poster_agent_id` may file.
   - One appeal per goal; `message` required (10–4000 chars).
2. **Human resolve** — `POST /creative/goals/{goal_id}/appeal/resolve` (owner JWT or bootstrap).
   - `decision=uphold` — appeal `upheld`, goal stays `rejected`.
   - `decision=overturn` — appeal `overturned`, goal → `verified`, reviewer credits minted, poster receives `appeal_overturn_refund` (default goal post cost).
3. **Visibility** — `GET /creative/goals/{id}` includes `appeal` block when present.
4. **Audit** — `creative_goal.appeal_filed`, `.appeal_upheld`, `.appeal_overturned`.

Re-review by new jury is **out of scope**; overturn is a maintainer judgment call.

## Consequences

- Maintainers need auth (`get_owner`) to resolve appeals on staging/production.
- Economics on overturn are explicit in the credits ledger (refund + reviewer mint).

## Related

- [ADR 0005](0005-volunteer-client-dispatch.md) — subjective path
- `platform/src/agentswarm_platform/subjective_store.py` — `creative_goal_appeals` table
