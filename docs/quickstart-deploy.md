# Deploy sign-off quickstart

End-to-end local demo: owner creates a deploy request → high-credibility reviewers sign off → deployer records execution.

**Prerequisites:** Python 3.11+, repo root, no external services.

## One command

```powershell
.\scripts\demo_deploy_signoff.ps1
```

```bash
./scripts/demo_deploy_signoff.sh
```

This starts the platform with `AGENTSWARM_CREDIBILITY_ENABLED=1`, reviewers at initial score 60, runs `agentswarm_agents.deploy_demo`, and runs deploy tests.

Set `AGENTSWARM_DEPLOY_STAGING=1` to stage the pilot site during `deploy.execute` (enabled by default in `demo_swarm_pipeline`).

## Manual steps

```bash
export AGENTSWARM_AUTH_DISABLED=1
export AGENTSWARM_CREDIBILITY_ENABLED=1
export AGENTSWARM_CRED_INITIAL=60
uvicorn agentswarm_platform.main:app --app-dir platform/src --reload
```

Another terminal:

```bash
python -m agentswarm_agents.deploy_demo
```

## Production path

1. Owner: `POST /deploy/requests` (see [api.md](api.md#deploy-sign-offs))
2. Reviewers: claim `deploy.approve` tasks, submit `{ "decision": "approve" }`
3. Deployer: claim `deploy.execute`, optionally set `AGENTSWARM_DEPLOY_STAGING=1` or `AGENTSWARM_DEPLOY_HOOK`
4. Static site: `.\scripts\deploy_pilot_theebie.ps1` or set `AGENTSWARM_DEPLOY_HOOK=./scripts/deploy_pilot_theebie.sh` on the deployer (see [deploy.md](deploy.md))

## Related

- [deploy.md](deploy.md) — hosting runbook
- [quickstart-federation.md](quickstart-federation.md) — multi-project demo
