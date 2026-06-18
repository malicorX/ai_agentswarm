# Task workflow — create, dispatch, solve

This guide describes the **decoupled task pool workflow**: enqueue goals, inspect swarm capacity, then let **volunteers** on worker machines execute assignments. The **task console** only dispatches (`create_task`); it does not run workers on the operator PC.

## Overview

| Step | Command | What happens |
|------|---------|--------------|
| 1. Enqueue | `create_task.ps1` | Reads a task file, posts a goal to the platform, returns `goal_id` |
| 2. Capacity | `GET /dispatch/capacity` | See which capabilities have idle/busy volunteers |
| 3. Work | `agentswarm-solve work --team engineering` | Long-running workers pick up assignments (on each machine) |
| 4. Execute | `start_task.ps1` **or** volunteers on worker machines | `start_task` runs a local team (dev); production uses `agentswarm-volunteer` per machine |

`agentswarm-solve` (all-in-one) still runs enqueue + local team + wait — useful for local dev. Production: **task console** or `create_task` to enqueue, **`agentswarm-volunteer`** on each worker machine. `start_task.ps1` is maintainer local all-in-one only.

## Task file format

Task files live under `tasks/` (any path works). Optional YAML-style frontmatter, then the brief body:

```text
---
goal_kind: engineering
fixture: primes
project_id: default
---
Create a Python script that writes out the first 100 primes, one per line.
```

### Frontmatter fields

| Field | Default | Description |
|-------|---------|-------------|
| `goal_kind` | `engineering` | `engineering` or `creative` |
| `fixture` | `primes` | Engineering-lab fixture (`primes`, `fizzbuzz`) |
| `lab` | `engineering-lab` | Lab namespace for verification |
| `project_id` | `default` | Platform project |
| `min_reviewers` | `1` (engineering) / `3` (creative) | Reviewer count |
| `pass_threshold` | platform default | Creative goals only |
| `dispatch_isolated` | `false` | When `true`, requires `dispatch_include_owners` |
| `dispatch_include_owners` | — | Comma-separated owner labels (dev demos) |
| `workspace_mode` | `local_fixture` | `local_fixture`, `sandbox`, or `git` (see below) |
| `workspace_repo_url` | — | SSH/HTTPS bare repo URL for `git` mode (else `AGENTSWARM_GIT_REPO_URL`) |
| `difficulty` | `1.0` | Credit pricing hint |

### Engineering workspace modes

| `workspace_mode` | Codewriter | Tester | Use when |
|------------------|------------|--------|----------|
| `local_fixture` (default) | Patches `pilot/engineering-lab/<fixture>/` via `AGENTSWARM_REPO_ROOT` | Host `pytest` (`tester` capability) | Local dev, single-machine `start_task` |
| `sandbox` | Same local fixture patch on the worker host | `pytest` inside Docker (`sandbox.linux` capability) | Safe compile/run/test without trusting host subprocess |

Sandbox goals use a **five-role** chain: coordinator → codewriter → **builder** (`compileall` in Docker) → tester (`pytest` in Docker) → reviewer.

First sandbox run builds `agentswarm/sandbox-pytest:3.12` from `pilot/engineering-lab/Dockerfile.sandbox` (pytest pre-installed; test containers still use `--network=none`).
| `git` | Clone goal repo, patch, push to `agentswarm/goal-<id>` branch | `pytest` on checked-out `workspace_ref` | Distributed handoff between machines |

A file with **no frontmatter** is treated as an engineering task on the `primes` fixture.

Examples:

- [tasks/example-primes.txt](../tasks/example-primes.txt) — `local_fixture`
- [tasks/example-primes-sandbox.txt](../tasks/example-primes-sandbox.txt) — `sandbox` (requires Docker)
- [tasks/example-primes-git.txt](../tasks/example-primes-git.txt) — `git` (requires Git)

**Git engineering** on staging:

```powershell
.\scripts\run_git_engineering.ps1
```

**Git on staging** (shared bare repo on theebie):

```powershell
.\scripts\run_git_engineering_staging.ps1 -InitGitWorkspace
```

Uses a local `file://` bare repo under `.agentswarm-git-workspaces/` unless `AGENTSWARM_GIT_REPO_URL` or `workspace_repo_url` is set.

**Distributed git (two sparkies)** — codewriter on sparky2, tester on sparky1:

```powershell
# No env setup required — defaults to theebie primes bare repo
.\scripts\demo_distributed_engineering_git.ps1

# After agent/platform changes
.\scripts\demo_distributed_engineering_git.ps1 -SyncRemotes
```

Sparkies need SSH access to `AGENTSWARM_GIT_REPO_URL` (typically `root@theebie.de:/var/lib/agentswarm/git-workspaces/primes.git`).

**Distributed git-in-container (D6)** — codewriter git on sparky2, sandbox tester on sparky1 (Docker or `AGENTSWARM_SANDBOX_MOCK=1` on sparky1):

```powershell
.\scripts\demo_distributed_engineering_sandbox_git.ps1 -SyncRemotes -InitGitWorkspace
```

## Create a task (enqueue only)

**Local platform** (auth disabled or bootstrap token set):

```powershell
.\scripts\create_task.ps1 -TaskFile tasks\example-primes.txt
```

```bash
agentswarm-create-task --task-file tasks/example-primes.txt
```

**Staging** (fetches bootstrap token from theebie):

```powershell
.\scripts\create_task_staging.ps1 -TaskFile tasks\example-primes.txt
```

**Staging execute** (fetches bootstrap + assignment secret):

```powershell
.\scripts\start_task_staging.ps1 -GoalId goal-a1b2c3d4e5f6
```

When using `start_task.ps1` directly against theebie, it auto-loads staging secrets if the base URL contains `theebie.de`.

**Output:**

```text
goal_id=goal-a1b2c3d4e5f6
coordinator_task_id=task-...
TaskId=goal-a1b2c3d4e5f6
status=pending
```

`TaskId` is an alias for `goal_id` (the platform uses opaque string IDs, not integers).

Requires `AGENTSWARM_BOOTSTRAP_TOKEN` or `AGENTSWARM_OWNER_TOKEN`. Does **not** start volunteer workers.

## Start a queued task (execute)

After `create_task`, run workers until the goal is verified:

```powershell
.\scripts\start_task.ps1 -GoalId goal-a1b2c3d4e5f6
```

```bash
agentswarm-start-task --goal-id goal-a1b2c3d4e5f6
```

This starts a local engineering volunteer team (coordinator → codewriter → tester → reviewer), waits until `/dispatch/capacity` shows idle workers for each role, then monitors `GET /creative/goals/{goal_id}` until `verified`.

Requires `AGENTSWARM_ASSIGNMENT_SECRET` in the environment (same as `agentswarm-solve work`).

**Recommended staging one-liner** (workers + isolated create + execute):

```powershell
.\scripts\run_task_staging.ps1 -TaskFile tasks\example-primes.txt
```

**Sandbox engineering** (Docker required; tester uses `sandbox.linux`):

```powershell
.\scripts\run_sandbox_engineering.ps1
# or explicitly:
$env:AGENTSWARM_SANDBOX = "1"
.\scripts\run_task_staging.ps1 -TaskFile tasks\example-primes-sandbox.txt
```

When using `--goal-id` from a prior `create_task`, `start_task` calls `POST /creative/goals/{id}/realign-dispatch` to reclaim assignments that landed on stale volunteer sessions. For sandbox goals, `start_task` registers the tester with `sandbox.linux` when the task file sets `workspace_mode: sandbox` or `AGENTSWARM_SANDBOX=1`.

**Full local example:**

```powershell
.\scripts\create_task.ps1 -TaskFile tasks\example-primes.txt
# note goal_id from output
.\scripts\start_task.ps1 -GoalId goal-...
```

## Check dispatch capacity

Owner-authenticated endpoint summarizing fresh volunteer presence:

```bash
curl -H "X-Bootstrap-Token: $AGENTSWARM_BOOTSTRAP_TOKEN" \
  https://theebie.de/agentswarm/api/dispatch/capacity
```

**Example response:**

```json
{
  "assignment_mode": "dispatch",
  "capabilities": {
    "coordinator": { "idle": 1, "busy": 0, "agents": [...] },
    "codewriter": { "idle": 0, "busy": 1, "agents": [...] },
    "reviewer": { "idle": 2, "busy": 0, "agents": [...] }
  },
  "totals": {
    "idle_agents": 3,
    "busy_agents": 1,
    "tracked_agents": 4
  }
}
```

Use this before `start_task` to see which roles need workers started.

## Automated test

The full **create goal → volunteer polls → submit → verified** chain is covered by live dispatch e2e tests (local uvicorn + real `VolunteerClient`):

| Test | What it mirrors |
|------|-----------------|
| `agents/tests/test_volunteer_dispatch_e2e.py::test_dispatch_goal_generalist_volunteer_primes_verified` | Task console dispatch + **one generalist volunteer** (solo machine) |
| `agents/tests/test_volunteer_dispatch_e2e.py::test_dispatch_goal_generalist_git_in_container_verified` | Same, for `git_in_container` (needs Docker) |
| `agents/tests/test_task_pool_chain_e2e.py::test_create_task_volunteer_chain_primes_verified` | Multi-role volunteer **team** (distributed-style) |

Run volunteer dispatch e2e only:

```bash
pytest agents/tests/test_volunteer_dispatch_e2e.py agents/tests/test_task_pool_chain_e2e.py -m dispatch_e2e
```

Included in `.\scripts\run_all_tests.ps1` (full `pytest agents/tests`).

## Run workers (pick up pool assignments)

On each volunteer machine:

```powershell
$env:AGENTSWARM_ASSIGNMENT_SECRET = "..."
agentswarm-solve work --team engineering
```

Workers heartbeat as idle, receive dispatch assignments, and execute capsules. Leave them running; `create_task` only enqueues work.

## Environment variables

| Variable | Used by |
|----------|---------|
| `AGENTSWARM_BOOTSTRAP_TOKEN` | `create_task` (post goals) |
| `AGENTSWARM_ASSIGNMENT_SECRET` | Volunteer workers (`work` mode) |
| `AGENTSWARM_STAGING_API_URL` | Staging scripts |
| `AGENTSWARM_PLATFORM_URL` | CLI default base URL |
| `AGENTSWARM_REPO_ROOT` | Repo root for engineering-lab fixture patches |
| `AGENTSWARM_GIT_REPO_URL` | Shared bare repo for `git` workspace mode |
| `AGENTSWARM_SANDBOX` | When `1`, `start_task` registers tester as `sandbox.linux` |
| `AGENTSWARM_CLIENT_DATA_DIR` | Volunteer model weights directory (see [volunteer-client.md](volunteer-client.md)) |
| `AGENTSWARM_WORKER_IMAGE` | Docker worker tag for `docker` runtime models |

## Task console

Operator web UI: `.\scripts\serve_task_console.ps1` → **Dispatch task** (enqueue only via `create_task`) or **Watch goal** on staging trace API.

The console machine **must not** execute capsules as a volunteer. Run `agentswarm-volunteer` on worker machines to take assignments. For local all-in-one dev use `start_task.ps1` instead.

### Project & replay (operator)

When watching a goal, the console **Project & replay** panel lets you:

1. **Browse** the workspace at `workspace_ref` (git checkout cached under `%LOCALAPPDATA%\AgentSwarm\replay-cache\`).
2. **Open files** (source, tests, docs) in a preview modal.
3. **Verify locally** — re-run pytest inside the same Linux sandbox image volunteers use (`agentswarm/sandbox-pytest:3.12`). Requires Docker on the operator PC.

CLI equivalent:

```powershell
agentswarm-replay-goal goal-… tree
agentswarm-replay-goal goal-… read primes.py
agentswarm-replay-goal goal-… verify
```

Distributed engineering goals should use `workspace_mode: git` (optionally `git_in_container: true`) so replay is authoritative across machines. `local_fixture` replay only reflects this machine's engineering-lab checkout.

## Related

- [Volunteer client](volunteer-client.md)
- [API reference — dispatch capacity](api.md#dispatch-capacity)
- [Getting started](getting-started.md)
- [ADR 0005 — volunteer dispatch](adr/0005-volunteer-client-dispatch.md)
