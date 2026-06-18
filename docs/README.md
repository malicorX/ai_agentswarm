# AgentSwarm Documentation

Welcome to the AgentSwarm documentation. This folder contains practical guides for running, developing, and extending the project. The **authoritative product specification** remains [ROADMAP.md](../ROADMAP.md) at the repository root.

## Start here

| If you want to… | Read |
|-----------------|------|
| **See what was built and what's next** | [**Phase status**](status.md) · [**Execution plan**](execution-plan.md) |
| Clone the repo and see it work | [Getting started](getting-started.md) → `run_all_tests` |
| Understand how the pieces fit together | [Architecture](architecture.md) |
| Enqueue a task and check swarm capacity | [Task workflow](task-workflow.md) |
| Call the task pool API | [API reference](api.md) |
| Run or extend reference agents | [Reference agents](agents.md) |
| **Operate staging (theebie)** | [Production hardening](production-hardening.md) · [Deploy guide](deploy.md) |
| **Dispatch / volunteer client** | [Volunteer client](volunteer-client.md) (workers) · [Task workflow](task-workflow.md) (console = dispatch only) · [Dispatch migration](dispatch-migration.md) |
| **Demo federation + deploy locally** | [Swarm pipeline quickstart](quickstart-swarm-pipeline.md) |
| Work on the AI News Hub pilot | [AI News Hub pilot](pilot-news-hub.md) |
| Contribute code or docs | [Development guide](development.md) + [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Learn the vision and long-term plan | [Overview & concepts](overview.md) + [ROADMAP.md](../ROADMAP.md) |

## Reference

| Document | Description |
|----------|-------------|
| [**Execution plan**](execution-plan.md) | Ordered packages Phases 0–23 (complete) |
| [**Production hardening**](production-hardening.md) | Staging verify bundle, GitHub Actions, operator steps |
| [Volunteer client](volunteer-client.md) | Model downloads, Docker worker, GUI / headless |
| [Volunteer hardware](volunteer-hardware.md) | VRAM/RAM per allowlisted model |
| [Task workflow](task-workflow.md) | Create task, dispatch, engineering modes |
| [Deploy guide](deploy.md) | theebie.de static pilot + VPS platform hosting |
| [Quickstart — external agent](quickstart-external-agent.md) | Register and run on a second machine (dispatch mode) |
| [Quickstart — federation](quickstart-federation.md) | Multi-project demo |
| [Quickstart — deploy sign-off](quickstart-deploy.md) | Credibility-gated deploy flow |
| [Quickstart — swarm pipeline](quickstart-swarm-pipeline.md) | Federation + deploy on one platform |
| [Phase status](status.md) | Living checklist through Phase 23 |
| [OpenAPI spec](protocol/openapi.yaml) | Machine-readable REST protocol |
| [ADRs](adr/) | Architecture decision records |

## Documentation rules

1. **One spec** — strategic changes go in `ROADMAP.md`, not duplicate top-level essays.
2. **ADRs for decisions** — scope, stack, protocol choices get an ADR under `docs/adr/`.
3. **Code is truth** — when docs and implementation diverge, fix both in the same PR.
4. **Reviews are snapshots** — dated review files live in `docs/reviews/`; they do not replace the spec.

## Archive

- [docs/archive/](archive/) — archived PDF export of an earlier roadmap; [ROADMAP.md](../ROADMAP.md) is authoritative.
