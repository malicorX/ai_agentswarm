# ADR 0009: Forge-agnostic git capsules (v1)

**Status:** Accepted  
**Date:** 2026-06-15  
**Spec:** [ROADMAP_CHANGES.md](../../ROADMAP_CHANGES.md) open question #7

## Context

P6.9 added git-backed coder capsules: volunteers clone a project repo, apply a bounded patch, commit, and push a branch. Hosting may be GitHub, GitLab, self-hosted Gitea/Forgejo, or a bare `git://` remote.

The open question was whether v1 should be **GitHub-first** (Octokit PR APIs, Actions hooks) or **forge-agnostic** (plain git protocol only).

## Decision

**v1 is forge-agnostic at the execution layer.**

| Layer | Behavior |
|-------|----------|
| **Execution** | Local `git` CLI only — `clone`, `commit`, `push` over the `repo_url` in the capsule |
| **`forge_type` field** | Metadata label on project config and `git_artifact` records — does **not** change client behavior in v1 |
| **Allowed values** | `git` (generic / self-hosted), `github`, `gitlab` |
| **Out of scope v1** | Forge REST APIs (open PR/MR via HTTP), GitHub Actions dispatch, GitLab pipeline triggers |

### Project configuration

`PATCH /projects/{id}/repo` stores:

| Field | Meaning |
|-------|---------|
| `repo_url` | Clone/push URL (HTTPS or SSH) understood by the volunteer's `git` |
| `default_branch` | Branch checked out before patch (default `main`) |
| `forge_type` | Hint for UI, audit, and future forge-specific integrations |

Self-hosted forges (Gitea, Forgejo, bare repos) use `forge_type=git`.

### Capsule flow (unchanged)

1. Dispatcher assigns `codewriter.patch` with `capsule.git` + `capsule.patch`.
2. Client runs `agentswarm_agents.git_capsule.execute_git_patch_capsule`.
3. Platform stores `git_artifact` on verified submit (`repo_url`, `branch`, `commit_sha`, `forge_type`).
4. Verifiers read `GET /submissions/{id}/git-artifact` — no forge API required.

### Authentication

Credentials are **not** managed by the platform in v1. Volunteers use:

- SSH keys or HTTPS tokens configured on the client machine, and/or
- `egress_allowlist` / maintainer-issued clone URLs with embedded read-only tokens (operator responsibility).

The platform never stores forge PATs for push in v1.

## Consequences

- GitHub and GitLab are first-class **labels**, not special code paths — same tests pass with `forge_type=github` or `gitlab`.
- A future package may add optional PR/MR creation behind `forge_type` without breaking generic `git` clients.
- Operators must ensure `repo_url` is reachable from volunteer machines; the platform does not proxy git traffic.

## Related

- [ADR 0005](0005-volunteer-client-dispatch.md) — dispatch assignments
- `agents/src/agentswarm_agents/git_capsule.py` — client executor
- `platform/src/agentswarm_platform/forge_types.py` — allowed `forge_type` values
- `platform/tests/test_git_patch.py` — e2e bare-repo patch flow
