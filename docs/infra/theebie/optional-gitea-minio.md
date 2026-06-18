# Optional Gitea + MinIO on theebie (D3)

The default distributed engineering path uses:

- **Git:** bare repo on theebie (`init_git_workspace_staging.ps1`) + per-goal forge deploy keys
- **Blobs:** platform `POST /artifacts` / `GET /artifacts/{sha256:…}` (content-addressed, deduped)

This optional stack adds a **web Git UI (Gitea)** and **S3-compatible blob store (MinIO)** for teams that want forge parity without external SaaS.

## Install

```powershell
.\scripts\install_optional_gitea_minio_staging.ps1
```

Services bind to **localhost only** on theebie (`127.0.0.1:3000` Gitea, `9000/9001` MinIO). Expose via Caddy if needed.

## Configure AgentSwarm

Point engineering goals at Gitea SSH URLs and set `forge_type` as usual. MinIO is not wired into the platform artifact store yet — use platform `/artifacts` or extend `AGENTSWARM_ARTIFACT_DIR` sync in a future slice.

## Defaults

| Service | URL | Notes |
|---------|-----|-------|
| Gitea | http://127.0.0.1:3000 | First-run admin setup in UI |
| MinIO API | http://127.0.0.1:9000 | Change `MINIO_ROOT_PASSWORD` in compose before production |
| MinIO console | http://127.0.0.1:9001 | |

Data directory: `/var/lib/agentswarm/optional-forge` (override with `AGENTSWARM_OPTIONAL_FORGE_DATA`).
