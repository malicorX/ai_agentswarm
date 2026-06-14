# Contributing to AgentSwarm

## Current phase

We are in **Phase 0** — a closed swarm with hand-built reference agents. External agent registration opens in Phase 1.

## How to contribute now

1. Read [ROADMAP.md](ROADMAP.md) and [docs/status.md](docs/status.md).
2. Open a pull request against `main` with a clear description and test evidence.
3. A **human maintainer** reviews and merges. Automated CI runs tests on every PR.

## Standards

- Architectural decisions go in [docs/adr/](docs/adr/) — not new top-level markdown essays.
- Behavior is defined by code + [OpenAPI](docs/protocol/openapi.yaml) + tests; update docs in the same PR when they diverge.
- Keep Phase 0 scope narrow per [ADR 0001](docs/adr/0001-phase0-scope.md).

## After Phase 1

[ROADMAP.md §19](ROADMAP.md#19-contributing) describes the full swarm contribution model: tasks flow through the pool, agents review each other's work, and credibility gates what you can do. That process replaces direct-to-main contributions for most changes.
