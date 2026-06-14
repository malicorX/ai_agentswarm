# ADR 0004: Phase 0 Stack Choice

**Status:** Accepted  
**Date:** 2026-06-13

## Context

Phase 0 needs a task pool service, cryptographic signature verification, tests, and reference agents. The roadmap allows Python (FastAPI) or Node (Fastify).

## Decision

Use **Python 3.11+** with:

| Layer | Choice |
|-------|--------|
| HTTP framework | FastAPI |
| ASGI server | uvicorn |
| Storage | SQLite (file-backed, single-node) |
| Crypto | `cryptography` (Ed25519) |
| Tests | pytest + httpx |

Reference agents share a thin Python client in `agents/` and run as CLI processes polling localhost.

## Rationale

- FastAPI generates OpenAPI from route definitions, keeping `docs/protocol/openapi.yaml` aligned.
- Ed25519 support is mature in `cryptography`.
- One language for platform + agents reduces Phase 0 friction; TypeScript SDK is Phase 1 (ADR 0003 dependent).

## Consequences

- Contributors need Python 3.11+ and a venv.
- Node is not required for Phase 0.
- SQLite path defaults to `platform/data/agentswarm.db` (gitignored).
