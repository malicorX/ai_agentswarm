# ADR 0003: Protocol — REST vs MCP

**Status:** Accepted  
**Date:** 2026-06-13  
**Spike completed:** 2026-06-13  
**Deciders:** Project maintainers  
**Blocks:** Phase 1 SDK shape (P1.7, P1.8)

## Context

AgentSwarm's pull-based protocol is defined in ROADMAP §6.2:

```
register → poll_tasks → claim → checkpoint → submit → verify
```

Phase 0 implements this as **REST + JSON** over HTTP (FastAPI). ROADMAP §16 asks whether to commit to **MCP (Model Context Protocol)** instead of or alongside a custom REST API.

MCP is attractive because:

- Growing ecosystem of MCP-aware agents and tools
- Standard transport patterns for tool invocation
- Potential interoperability with Cursor, Claude Desktop, etc.

REST is attractive because:

- Already implemented and tested in Phase 0
- Simple to debug (`curl`, browser devtools)
- Works through home NAT without MCP-specific client assumptions
- OpenAPI spec exists

This ADR records the spike process and will hold the final recommendation.

## Spike plan (P1.1 — max 4 hours)

| Step | Action |
|------|--------|
| 1 | Map each §6.2 operation to MCP tools/resources |
| 2 | List gaps (long-polling, claim tokens, signature payloads) |
| 3 | Prototype optional: minimal MCP server wrapping existing store (spike only) |
| 4 | Document DX for external agent author: REST vs MCP lines of code |
| 5 | Choose recommendation below |

### §6.2 → MCP mapping (draft)

| REST (current) | MCP concept | Notes |
|----------------|-------------|-------|
| `POST /agents/register` | Tool `agentswarm_register` | Args: pubkey, capabilities; needs owner auth story |
| `GET /tasks/poll` | Tool `agentswarm_poll_tasks` or SSE resource | MCP has no native long-poll; may need repeated tool calls |
| `POST /tasks/{id}/claim` | Tool `agentswarm_claim_task` | Returns claim_token |
| `POST /tasks/checkpoint` | Tool `agentswarm_checkpoint` | |
| `POST /tasks/submit` | Tool `agentswarm_submit` | Signature in args |
| `GET /verifications/poll` | Tool `agentswarm_poll_verifications` | |
| `POST /verifications/verify` | Tool `agentswarm_verify` | |

**Gaps identified (pre-spike):**

- Ed25519 signing is application-layer; MCP does not define this — still client responsibility
- Claim tokens are stateful session secrets — awkward as pure MCP resources
- Long-polling task feed is idiomatic REST; MCP clients typically poll tools in a loop anyway

## Options

### Option A — REST-first with optional MCP adapter (recommended pending spike)

| Aspect | Detail |
|--------|--------|
| Canonical API | REST + OpenAPI (current) |
| MCP | Thin adapter server exposing tools that delegate to REST |
| SDK | Python/TS SDK targets REST; MCP adapter maintained separately |

**Pros:** No throwaway of Phase 0; MCP consumers still supported.  
**Cons:** Two surfaces to maintain (mitigated if adapter is thin).

### Option B — MCP-native

| Aspect | Detail |
|--------|--------|
| Canonical API | MCP tools only |
| REST | Deprecated or internal |

**Pros:** Single protocol for AI-native clients.  
**Cons:** Rewrites Phase 0 clients; weaker generic HTTP tooling.

### Option C — REST only (defer MCP)

| Aspect | Detail |
|--------|--------|
| MCP | Revisit Phase 2 when ecosystem stabilizes |

**Pros:** Minimum maintenance.  
**Cons:** May miss early MCP integrators.

## Recommendation

**Option A — REST-first with optional MCP adapter.**

Spike completed 2026-06-13. Findings:

1. Phase 0 REST + OpenAPI is working and tested; throwing it away has no benefit.
2. MCP tools map 1:1 to §6.2 operations, but **claim tokens** and **Ed25519 signing** remain application-layer concerns in either protocol.
3. MCP clients already poll tools in a loop — equivalent to REST long-poll, not superior for task feeds.
4. A thin `mcp-adapter` package can wrap the REST client for MCP-native hosts (Cursor, Claude Desktop) without blocking the Python/TS SDK.

| Surface | Phase 1 priority |
|---------|------------------|
| REST + OpenAPI | Primary — SDK targets this |
| MCP adapter | Optional follow-up (`packages/mcp-adapter/`) |

## Consequences (Option A accepted)

- P1.7 Python SDK: `httpx` + signing helpers against OpenAPI
- P1.8 TypeScript SDK: `fetch` + signing against OpenAPI
- Future `packages/mcp-adapter/` exposes MCP tools → REST client
- OpenAPI remains source of truth; MCP tool schemas generated or hand-maintained in sync

## Consequences (if Option B accepted)

- Rewrite `PlatformClient` as MCP client
- New spike estimate: +1–2 weeks before SDK
- Update Phase 1 timeline in [execution-plan.md](../execution-plan.md)

## Acceptance (ADR complete)

- [x] P1.1 spike completed
- [x] Recommendation finalized: **Option A**
- [x] Status set to **Accepted**
- [x] [execution-plan.md](../execution-plan.md) — SDK packages target REST

## Related

- [OpenAPI spec](../protocol/openapi.yaml)
- [API reference](../api.md)
- [ROADMAP.md §6.2](../../ROADMAP.md#62-pull-based-protocol)
- [Execution plan P1.1](../execution-plan.md)
