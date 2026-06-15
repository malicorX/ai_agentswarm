# ADR 0007: Volunteer model allowlist

**Status:** Accepted  
**Date:** 2026-06-15  
**Spec:** [ROADMAP_CHANGES.md](../../ROADMAP_CHANGES.md) invariant N8, open question #2

## Context

Production volunteer clients must not call arbitrary LLM endpoints. The platform publishes the canonical list; clients bundle the same list and cross-check at connect time.

## Decision

### Allowlist format (version 2)

Each entry in `model_allowlist.json`:

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | yes | Stable identifier sent as `model_id` on presence heartbeats |
| `label` | yes | Human-readable name for the volunteer GUI |
| `runtime` | yes | `in-process`, `docker`, or `ollama` |
| `endpoint` | ollama only | Must be `http://127.0.0.1:*` or `http://localhost:*` |
| `local_only` | recommended for ollama | Documents that remote inference is forbidden |

Bundled GGUF weights are **not** in v2; use `docker` runtime with a worker image that mounts local weights, or `ollama` with a localhost endpoint.

### Publication

- **Platform:** `GET /platform/config` → `models.allowlist`, `models.enforced`
- **Client:** `agentswarm_agents/model_allowlist.json` (must match platform file byte-for-byte; tested in CI)

### Enforcement

| Layer | Behavior |
|-------|----------|
| Client | `validate_model_id()` always when `AGENTSWARM_ALLOWLIST_SKIP` unset |
| Client connect | `assert_platform_model_allowlist()` — model must appear on platform list |
| Platform presence | Rejects unknown `model_id` when `AGENTSWARM_MODEL_ALLOWLIST_ENFORCE=1` |

Default: platform enforcement **off** (staging/dev); production should set `AGENTSWARM_MODEL_ALLOWLIST_ENFORCE=1`.

### Runtimes

| Runtime | Status |
|---------|--------|
| `in-process` | Mock/dev executor (`llm-mock-v1`) |
| `docker` | Worker image (`llm-docker-worker-v1`) |
| `ollama` | Listed for forward compatibility; executor not implemented yet |

## Consequences

- Adding a model requires updating both JSON copies and redeploying platform + client builds.
- Cloud LLM proxies are out of scope unless they bind to localhost only.

## Related

- [ADR 0005](0005-volunteer-client-dispatch.md)
- `platform/src/agentswarm_platform/model_allowlist.py`
- `agents/src/agentswarm_agents/model_allowlist.py`
