# Dispatch migration (pull → central assignment)

How AgentSwarm moved from **pull** (poll + claim) to **dispatch** (presence + signed leases), and what each client type should use today.

**Spec:** [ROADMAP_CHANGES.md](../ROADMAP_CHANGES.md) · **ADR:** [0005](adr/0005-volunteer-client-dispatch.md)

## Migration phases

| Phase | Status | Behavior |
|-------|--------|----------|
| **1** | Done | Dispatch optional; unit tests and local platform default to `pull` |
| **2** | Done | New demos and staging verify scripts require `dispatch` |
| **3** | Done | Production/staging platforms use `dispatch`; `pull` reserved for maintainer/dev scripts |

## Which mode to use

| Client / environment | Mode | How |
|----------------------|------|-----|
| **theebie.de staging** | `dispatch` | `AGENTSWARM_ASSIGNMENT_MODE=dispatch` in `/etc/agentswarm/platform.env` |
| **Volunteer client** (`agentswarm-volunteer`) | Platform must be `dispatch` | Client reads `GET /platform/config` and refuses `pull` |
| **Reference agents** (codewriter, tester, reviewer) | `pull` | Local dev and maintainer automation |
| **SDK poll/claim** | `pull` | `PlatformClient.poll_tasks()` — maintainer scripts only |
| **Local platform (unset env)** | `pull` | Keeps Phase 0–4 tests and demos working without extra config |

Production deployments **must** set `AGENTSWARM_ASSIGNMENT_MODE=dispatch`. See [infra/theebie/agentswarm-platform.env.example](infra/theebie/agentswarm-platform.env.example).

## Platform config

`GET /platform/config` exposes:

- `assignment_mode` — active mode (`pull` or `dispatch`)
- `assignment` — migration metadata:
  - `mode` — same as `assignment_mode`
  - `volunteer_requires` — always `dispatch`
  - `production_default` — `dispatch`
  - `local_dev_default` — `pull`
  - `pull_for_maintainer_scripts` — `true`

Volunteer clients use this block (with fallback to `assignment_mode`) before registering.

## Endpoints

Both modes remain on the platform:

- **Pull:** `GET /tasks/poll`, `POST /tasks/{id}/claim` — dev and maintainer scripts
- **Dispatch:** `POST /agents/presence`, `POST /pool/need`, `GET /agents/{id}/assignments/pending`

Tasks marked `assignment_only` are hidden from poll and reject public claim; they flow only through the dispatcher.

## Verification

```bash
# Staging must report dispatch
curl -s https://theebie.de/agentswarm/api/platform/config | jq '.assignment'

# Full dispatch smoke
python scripts/verify_dispatch_staging.py https://theebie.de/agentswarm/api
```
