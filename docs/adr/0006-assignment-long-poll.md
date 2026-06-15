# ADR 0006: Assignment delivery — long-poll first

**Status:** Accepted  
**Date:** 2026-06-15  
**Spec:** [ROADMAP_CHANGES.md](../../ROADMAP_CHANGES.md) open question #1

## Context

Dispatch clients must wait for the platform to assign work. Client-side tight polling (`GET /assignments/pending` in a loop) wastes bandwidth and adds latency.

ROADMAP_CHANGES proposed `GET /agents/assignments/wait` for server-side long-poll. WebSocket delivery is deferred.

## Decision

1. **Server-side long-poll** on assignment fetch:
   - `GET /agents/{id}/assignments/pending?wait_sec=N` — `wait_sec=0` (default) preserves immediate behavior.
   - `GET /agents/{id}/assignments/wait?wait_sec=N` — alias with default `wait_sec=30`.
2. **Caps** via `AGENTSWARM_ASSIGNMENT_LONG_POLL_MAX_SEC` (default `60`) and poll interval `AGENTSWARM_ASSIGNMENT_LONG_POLL_INTERVAL_SEC` (default `0.25`).
3. **Public config** exposes `dispatch.long_poll_max_sec` when `assignment_mode=dispatch`.
4. **Clients** (`DispatchClient.wait_for_assignment`) use one long-poll request by default (`server_long_poll=True`); client-side polling remains as fallback.

WebSocket assignment push is **out of scope** until long-poll proves insufficient at scale.

## Consequences

- Sync request handlers may block up to `wait_sec` per waiting client; acceptable for staging and early volunteer scale.
- Reverse proxies must allow request timeouts ≥ client `wait_sec` (Caddy defaults are fine for ≤60s).
- Existing callers of `/assignments/pending` without `wait_sec` are unchanged.

## Related

- [ADR 0005](0005-volunteer-client-dispatch.md) — dispatch mode
- `platform/src/agentswarm_platform/assignment_wait.py`
