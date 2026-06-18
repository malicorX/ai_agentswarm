# Full staging deploy e2e: engineering goal verify + optional deploy sign-off chain.
param(
    [string]$ApiUrl = $(if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }),
    [switch]$SignoffChain,
    [switch]$ExecuteDeploy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$HostSsh = if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }
$EnvFile = if ($env:AGENTSWARM_PLATFORM_ENV_FILE) { $env:AGENTSWARM_PLATFORM_ENV_FILE } else { "/etc/agentswarm/platform.env" }

if (-not $env:AGENTSWARM_BOOTSTRAP_TOKEN) {
    $env:AGENTSWARM_BOOTSTRAP_TOKEN = (ssh $HostSsh "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' $EnvFile | cut -d= -f2-").Trim()
}
if (-not $env:AGENTSWARM_ASSIGNMENT_SECRET) {
    $env:AGENTSWARM_ASSIGNMENT_SECRET = (ssh $HostSsh "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' $EnvFile | cut -d= -f2-").Trim()
}

$env:AGENTSWARM_STAGING_API_URL = $ApiUrl
$env:AGENTSWARM_VERIFY_DEPLOY_E2E_ENGINEERING = "1"
$env:AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL = "1"
if ($SignoffChain) { $env:AGENTSWARM_VERIFY_DEPLOY_SIGNOFF_CHAIN = "1" }
if ($ExecuteDeploy) { $env:AGENTSWARM_VERIFY_DEPLOY_EXECUTE = "1" }

python scripts/verify_staging_deploy_e2e.py $ApiUrl
exit $LASTEXITCODE
