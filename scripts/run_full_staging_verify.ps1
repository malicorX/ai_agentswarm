# Run the full staging verification bundle against theebie.de (P7.4).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

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

$env:AGENTSWARM_VERIFY_FULL = "1"
$env:AGENTSWARM_EXPECT_DISPATCH = "1"
$env:AGENTSWARM_EXPECT_REGISTRATION_AUTH = "1"
if (-not $env:AGENTSWARM_VERIFY_SUBJECTIVE_MIN_REVIEWERS) {
    $env:AGENTSWARM_VERIFY_SUBJECTIVE_MIN_REVIEWERS = "1"
}
$env:AGENTSWARM_STAGING_API_URL = $ApiUrl

python scripts/verify_production_staging.py $ApiUrl
Write-Host "Full staging verify OK: $ApiUrl"
