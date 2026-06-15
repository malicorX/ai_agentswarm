# ADR 0005: Volunteer Client & Central Dispatch (Phase 6)

**Status:** Accepted  
**Date:** 2026-06-15  
**Spec:** [ROADMAP_CHANGES.md](../../ROADMAP_CHANGES.md)

## Context

Phases 0–4 deliver a pull-based task pool: agents poll and claim work. The Phase 6 product direction requires:

- Compute on volunteer clients only (SETI@home model).
- Clients must not pick tasks or roles; theebie.de assigns work.
- Reviewers and other verification roles must not be self-assigned by task posters.
- Assignments are signed; tasks are encapsulated in capsules.

## Decision

### Assignment modes

| Mode | Env | Behavior |
|------|-----|----------|
| **pull** (default) | `AGENTSWARM_ASSIGNMENT_MODE=pull` | Existing poll + claim (Phases 0–4) |
| **dispatch** | `AGENTSWARM_ASSIGNMENT_MODE=dispatch` | Presence registry + dispatcher assigns leases |

Default remains **pull** until dispatch path is tested in CI.

### Platform components (dispatch mode)

1. **`POST /agents/presence`** — client heartbeat (idle/busy, capabilities, model_id, TTL).
2. **`POST /pool/need`** — request a role for a task (creates `pool_needs` row).
3. **Dispatcher** — selects idle agent (owner disjoint from excluded owners), creates signed assignment lease, claims task internally.
4. **`GET /agents/{id}/assignments/pending`** — client fetches active assignment.
5. **Tasks with `assignment_only`** — hidden from poll; reject public claim.

### Signing

Assignment leases signed with HMAC-SHA256 (`AGENTSWARM_ASSIGNMENT_SECRET`, fallback `AGENTSWARM_SESSION_SECRET`).

### Out of scope (later packages)

- Desktop `.exe` client — shipped in P6.8 (`agentswarm-volunteer`).
- Docker worker — shipped in P6.6.
- Credits ledger — shipped in P6.4.
- Subjective quorum — shipped in P6.3.

## Consequences

- Existing demos and tests continue with `pull` mode.
- New dispatch tests run with `AGENTSWARM_ASSIGNMENT_MODE=dispatch`.
- `claim_task` rejects `assignment_only` tasks unless assigned via dispatcher.

## Related

- [ROADMAP_CHANGES.md](../../ROADMAP_CHANGES.md) — full Phase 6 plan.
