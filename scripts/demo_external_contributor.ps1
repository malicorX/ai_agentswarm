param(
    [string]$PlatformUrl = $(if ($env:AGENTSWARM_PLATFORM_URL) { $env:AGENTSWARM_PLATFORM_URL } elseif ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $env:AGENTSWARM_BOOTSTRAP_TOKEN) {
    Write-Host "Tip: set AGENTSWARM_BOOTSTRAP_TOKEN to run the maintainer enqueue + codewriter task flow."
}

python scripts/verify_external_contributor.py $PlatformUrl
exit $LASTEXITCODE
