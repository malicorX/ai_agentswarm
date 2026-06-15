# ADR 0005: Volunteer Client & Central Dispatch (Phase 6)

**Status:** Accepted  
**Date:** 2026-06-15  
**Updated:** 2026-06-13 (migration phase 3)  
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
| **pull** | `AGENTSWARM_ASSIGNMENT_MODE=pull` | Poll + claim (Phases 0–4); **maintainer/dev scripts only** after migration phase 3 |
| **dispatch** | `AGENTSWARM_ASSIGNMENT_MODE=dispatch` | Presence registry + dispatcher assigns leases; **required for production/staging and volunteer clients** |

When `AGENTSWARM_ASSIGNMENT_MODE` is unset, the platform defaults to **pull** so local unit tests and reference agents work without extra configuration. Production deployments (theebie.de) set **dispatch** explicitly.

Migration phase 3 is complete — see [dispatch-migration.md](../dispatch-migration.md).

### Platform components (dispatch mode)

1. **`POST /agents/presence`** — client heartbeat (idle/busy, capabilities, model_id, TTL).
2. **`POST /pool/need`** — request a role for a task (creates `pool_needs` row).
3. **Dispatcher** — selects idle agent (owner disjoint from excluded owners), creates signed assignment lease, claims task internally.
4. **`GET /agents/{id}/assignments/pending`** — client fetches active assignment.
5. **Tasks with `assignment_only`** — hidden from poll; reject public claim.

### Config surface

`GET /platform/config` includes `assignment_mode` and an `assignment` metadata block (`volunteer_requires`, `production_default`, `local_dev_default`, `pull_for_maintainer_scripts`) so clients can validate posture before registering.

### Signing

Assignment leases signed with HMAC-SHA256 (`AGENTSWARM_ASSIGNMENT_SECRET`, fallback `AGENTSWARM_SESSION_SECRET`).

### Out of scope (later packages)

- Desktop `.exe` client — shipped in P6.8 (`agentswarm-volunteer`).
- Docker worker — shipped in P6.6.
- Credits ledger — shipped in P6.4.
- Subjective quorum — shipped in P6.3.

## Consequences

- Local demos and Phase 0–4 tests continue with default `pull` mode.
- Staging and production **must** run `dispatch`; volunteer clients refuse `pull` platforms.
- New dispatch tests run with `AGENTSWARM_ASSIGNMENT_MODE=dispatch`.
- `claim_task` rejects `assignment_only` tasks unless assigned via dispatcher.
- SDK `poll_tasks` / MCP poll tools remain for maintainer automation, not volunteer production paths.

## Related

- [ROADMAP_CHANGES.md](../../ROADMAP_CHANGES.md) — full Phase 6 plan.
- [dispatch-migration.md](../dispatch-migration.md) — pull vs dispatch client guide.
