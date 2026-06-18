# Engineering goal demo against staging (coordinator → codewriter → tester → reviewer).
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
    $env:AGENTSWARM_BOOTSTRAP_TOKEN = $boot.Trim().Trim([char]13)
}

if (-not $env:AGENTSWARM_ASSIGNMENT_SECRET) {
    $secret = ssh $HostSsh "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' $EnvFile | cut -d= -f2-"
    if (-not $secret) {
        Write-Error "Could not read AGENTSWARM_ASSIGNMENT_SECRET from ${HostSsh}:${EnvFile}"
    }
    $env:AGENTSWARM_ASSIGNMENT_SECRET = $secret.Trim().Trim([char]13)
}

$env:AGENTSWARM_STAGING_API_URL = $ApiUrl
python scripts/demo_engineering_goal.py --base-url $ApiUrl @args
exit $LASTEXITCODE
