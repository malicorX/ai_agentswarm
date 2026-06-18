# Verified goal → production deploy (D5)
#
# Prerequisite: a verified engineering goal with artifact_refs (sandbox log bundle or git workspace_ref).
# Uses owner auth (AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN).

param(
    [Parameter(Mandatory = $true)]
    [string]$GoalId,
    [string]$Environment = "staging",
    [string]$Description = "Deploy from verified goal"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $env:AGENTSWARM_STAGING_API_URL) {
    Write-Error "Set AGENTSWARM_STAGING_API_URL"
}

python -c @"
import json, os, sys
import httpx

goal_id = sys.argv[1]
environment = sys.argv[2]
description = sys.argv[3]
base = os.environ['AGENTSWARM_STAGING_API_URL'].rstrip('/')
token = os.environ.get('AGENTSWARM_BOOTSTRAP_TOKEN') or os.environ.get('AGENTSWARM_OWNER_TOKEN')
if not token:
    raise SystemExit('set AGENTSWARM_BOOTSTRAP_TOKEN or AGENTSWARM_OWNER_TOKEN')
headers = {'Authorization': f'Bearer {token}'}
with httpx.Client(timeout=60, follow_redirects=True) as client:
    goal = client.get(f'{base}/creative/goals/{goal_id}', headers=headers).json()
    print('goal_status=', goal.get('status'))
    print('primary_artifact_ref=', goal.get('primary_artifact_ref'))
    print('artifact_refs=', goal.get('artifact_refs'))
    if goal.get('status') != 'verified':
        raise SystemExit('goal must be verified before deploy-request')
    resp = client.post(
        f'{base}/creative/goals/{goal_id}/deploy-request',
        headers=headers,
        json={'environment': environment, 'description': description, 'required_signoffs': 2},
    )
    print(resp.status_code, resp.text)
    resp.raise_for_status()
    body = resp.json()
    print('deploy_request_id=', body['request_id'])
    print('artifact_ref=', body['artifact_ref'])
"@ $GoalId $Environment $Description
