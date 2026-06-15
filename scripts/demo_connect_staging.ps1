# Smoke-test external connectivity to theebie staging API (presence heartbeat).
param(
    [string]$ApiUrl = $(if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python scripts/verify_staging_api.py $ApiUrl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:AGENTSWARM_PLATFORM_URL = $ApiUrl
agentswarm-volunteer --headless --loops 1 --base-url $ApiUrl
exit $LASTEXITCODE
