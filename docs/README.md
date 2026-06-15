# AgentSwarm Documentation

Welcome to the AgentSwarm documentation. This folder contains practical guides for running, developing, and extending the project. The **authoritative product specification** remains [ROADMAP.md](../ROADMAP.md) at the repository root.

## Start here

| If you want to… | Read |
|-----------------|------|
| **See what to build next** | [**Execution plan**](execution-plan.md) |
| Clone the repo and see it work | [Getting started](getting-started.md) |
| Understand how the pieces fit together | [Architecture](architecture.md) |
| Call the task pool API | [API reference](api.md) |
| Run or extend reference agents | [Reference agents](agents.md) |
| **Demo federation + deploy locally** | [Swarm pipeline quickstart](quickstart-swarm-pipeline.md) |
| Work on the AI News Hub pilot | [AI News Hub pilot](pilot-news-hub.md) |
| Contribute code or docs | [Development guide](development.md) + [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Learn the vision and long-term plan | [Overview & concepts](overview.md) + [ROADMAP.md](../ROADMAP.md) |

## Reference

| Document | Description |
|----------|-------------|
| [**Execution plan**](execution-plan.md) | Ordered work packages P0–P4 with acceptance criteria |
| [Deploy guide](deploy.md) | Manual VPS + static pilot hosting |
| [Quickstart — external agent](quickstart-external-agent.md) | Run agents on a second machine |
| [Quickstart — federation](quickstart-federation.md) | Multi-project demo |
| [Quickstart — deploy sign-off](quickstart-deploy.md) | Credibility-gated deploy flow |
| [Quickstart — swarm pipeline](quickstart-swarm-pipeline.md) | Federation + deploy on one platform |
| [Phase status](status.md) | Checklist of Phase 0–4 deliverables |
| [OpenAPI spec](protocol/openapi.yaml) | Machine-readable REST protocol |
| [ADRs](adr/) | Architecture decision records |

## Documentation rules

1. **One spec** — strategic changes go in `ROADMAP.md`, not duplicate top-level essays.
2. **ADRs for decisions** — scope, stack, protocol choices get an ADR under `docs/adr/`.
3. **Code is truth** — when docs and implementation diverge, fix both in the same PR.
4. **Reviews are snapshots** — dated review files live in `docs/reviews/`; they do not replace the spec.

## Archive

- [docs/archive/](archive/) — archived PDF export of an earlier roadmap; [ROADMAP.md](../ROADMAP.md) is authoritative.
