# Phase 7 close-out: unit tests + live dispatch smoke on theebie (P7.11).
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

$env:AGENTSWARM_EXPECT_DISPATCH = "1"
python scripts/verify_dispatch_staging.py $ApiUrl

Write-Host "Phase 7 close-out checks OK. Tag with:"
Write-Host "  git tag v0.8.0-phase7 && git push origin v0.8.0-phase7"
