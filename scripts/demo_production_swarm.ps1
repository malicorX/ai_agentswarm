param(
    [string]$PlatformUrl = $(if ($env:AGENTSWARM_PLATFORM_URL) { $env:AGENTSWARM_PLATFORM_URL } else { "https://theebie.de/agentswarm/api" }),
    [string]$BootstrapToken = $env:AGENTSWARM_BOOTSTRAP_TOKEN
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($BootstrapToken) { $env:AGENTSWARM_BOOTSTRAP_TOKEN = $BootstrapToken }
$env:AGENTSWARM_PLATFORM_URL = $PlatformUrl

python scripts/verify_production_swarm.py $PlatformUrl
exit $LASTEXITCODE
