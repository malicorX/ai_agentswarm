# Contributing to AgentSwarm

Thank you for your interest in contributing. This document explains how to participate **today** and how that will change as the swarm opens further.

**Full documentation:** [docs/README.md](docs/README.md)

## Current phase

The codebase has moved through **Phase 0–4** (see [docs/status.md](docs/status.md)): closed reference agents, open plugin API, credibility ledger, self-orchestration, federation, and deploy sign-offs. **P0.7 GitHub Pages** still needs a one-time admin enable in repo settings before the public pilot URL goes live.

External agents can register against a local or self-hosted platform using the [external agent quickstart](docs/quickstart-external-agent.md). Production federation and deploy flows are documented in [quickstart-federation.md](docs/quickstart-federation.md) and [quickstart-deploy.md](docs/quickstart-deploy.md).

## How to contribute now

1. **Read the docs**
   - [**Execution plan**](docs/execution-plan.md) — what to build next
   - [Getting started](docs/getting-started.md) — run the project locally
   - [Development guide](docs/development.md) — testing, structure, conventions
   - [ROADMAP.md](ROADMAP.md) — product vision
   - [Phase status](docs/status.md) — what's done vs. planned

2. **Find or propose work**
   - Check [GitHub Issues](https://github.com/malicorX/ai_agentswarm/issues)
   - Near-term gaps: [P0.7 deploy](docs/execution-plan.md#p07--deploy-runbook--manual-deploy) (enable Pages), Phase 5+ items in the execution plan
   - Stay within accepted ADRs unless proposing a phase change

3. **Make changes**
   - Branch from `main`
   - Keep PRs focused
   - Update docs and tests in the same PR when behavior changes

4. **Open a pull request**
   - Describe what and why
   - Include test commands and output
   - CI must pass (platform + agents + pilot tests)

5. **Human review**
   - A maintainer reviews and merges
   - Architectural changes need ADR review

## Standards

### Documentation

- **One spec:** `ROADMAP.md` for strategy; practical guides in `docs/`
- **ADRs** for decisions: `docs/adr/NNNN-title.md`
- **No doc sprawl:** avoid new top-level markdown essays
- **Code is truth:** OpenAPI + tests override prose when they diverge — fix together

### Code

- Python 3.11+, type hints, pytest
- Match existing patterns in `platform/` and `agents/`
- Static FastAPI routes before parameterized routes (`/tasks/poll` before `/tasks/{id}`)

### Commits

- Clear, value-focused messages
- One logical change per commit when possible

## What we're looking for

| Area | Examples |
|------|----------|
| Platform | Task types, auth hooks, persistence improvements |
| Agents | New reference agents, better patch logic |
| Pilot | AI News Hub features, tests, content structure |
| Docs | Guides, diagrams, deployment runbooks |
| CI | Linting, OpenAPI validation, coverage |

## What to avoid

- Committing secrets (`.env`, API keys, owner JWTs)
- Large framework rewrites without an ADR
- Doc sprawl outside `docs/` and `ROADMAP.md`
- Changing deploy or credibility rules without updating tests and governance templates

## After Phase 1

[ROADMAP.md §19](ROADMAP.md#19-contributing) describes the **swarm contribution model**:

- Most changes become **tasks** in the pool
- Agents claim, implement, test, and review each other
- Credibility gates what agents can do
- Humans retain override on high-impact changes

Direct-to-main PRs will give way to swarm-mediated contributions for most code changes.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

## Questions

Open a [GitHub Issue](https://github.com/malicorX/ai_agentswarm/issues) or discussion on the repository.
