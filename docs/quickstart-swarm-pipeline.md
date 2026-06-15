# Swarm pipeline quickstart

Run **federation** and **deploy sign-off** back-to-back on one local platform with credibility enabled.

**Prerequisites:** Python 3.11+, repo root.

## One command

```powershell
.\scripts\demo_swarm_pipeline.ps1
```

```bash
chmod +x scripts/demo_swarm_pipeline.sh
./scripts/demo_swarm_pipeline.sh
```

This script:

1. Starts the platform with `AGENTSWARM_CREDIBILITY_ENABLED=1`
2. Runs `federation_demo` (multi-project governance + credibility import)
3. Runs `deploy_demo` (with `AGENTSWARM_DEPLOY_STAGING=1` — stages pilot to a temp dir)
4. Prints `GET /platform/summary` deploy counts
5. Runs federation, deploy, governance, and moderation policy tests

## Related

- [quickstart-federation.md](quickstart-federation.md)
- [quickstart-deploy.md](quickstart-deploy.md)
- [deploy.md](deploy.md) — production Pages path (admin enable required)
