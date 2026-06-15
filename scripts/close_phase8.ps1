# Phase 8 close-out: unit tests + dispatch smoke + volunteer subjective demo (P8.11).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pytest -q platform/tests agents/tests

$HostSsh = if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }
$EnvFile = if ($env:AGENTSWARM_PLATFORM_ENV_FILE) { $env:AGENTSWARM_PLATFORM_ENV_FILE } else { "/etc/agentswarm/platform.env" }
$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }

if (-not $env:AGENTSWARM_BOOTSTRAP_TOKEN) {
    $boot = ssh $HostSsh "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' $EnvFile | cut -d= -f2-"
    if (-not $boot) {
        Write-Error "Could not read AGENTSWARM_BOOTSTRAP_TOKEN from ${HostSsh}:${EnvFile}"
    }
    $env:AGENTSWARM_BOOTSTRAP_TOKEN = $boot.Trim()
}

if (-not $env:AGENTSWARM_ASSIGNMENT_SECRET) {
    $secret = ssh $HostSsh "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' $EnvFile | cut -d= -f2-"
    if (-not $secret) {
        Write-Error "Could not read AGENTSWARM_ASSIGNMENT_SECRET from ${HostSsh}:${EnvFile}"
    }
    $env:AGENTSWARM_ASSIGNMENT_SECRET = $secret.Trim()
}

$env:AGENTSWARM_EXPECT_DISPATCH = "1"
python scripts/verify_dispatch_staging.py $ApiUrl

powershell -File scripts/demo_volunteer_subjective_staging.ps1 -min-reviewers 1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Phase 8 close-out checks OK. Tag with:"
Write-Host "  git tag v0.9.0-phase8 && git push origin v0.9.0-phase8"
