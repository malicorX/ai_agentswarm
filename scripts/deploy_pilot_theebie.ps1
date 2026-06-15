param(
    [string]$TheebieHost = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$RemoteDir = $(if ($env:AGENTSWARM_THEEBIE_DIR) { $env:AGENTSWARM_THEEBIE_DIR } else { "/var/www/html/sites/agentswarm" }),
    [string]$TargetUrl = $(if ($env:AGENTSWARM_DEPLOY_TARGET_URL) { $env:AGENTSWARM_DEPLOY_TARGET_URL } else { "https://theebie.de/sites/agentswarm" }),
    [switch]$RecordUrl
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$staging = if ($env:AGENTSWARM_PILOT_STAGING_DIR) { $env:AGENTSWARM_PILOT_STAGING_DIR } else { Join-Path $Root "dist\pilot-site" }

python scripts/stage_pilot_site.py --output $staging
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

ssh $TheebieHost "mkdir -p '$RemoteDir'"
scp -r "$staging\*" "${TheebieHost}:${RemoteDir}/"

Write-Host "Deployed pilot site to ${TheebieHost}:${RemoteDir}" -ForegroundColor Green
Write-Host "Live URL: ${TargetUrl}/"

if ($RecordUrl -or $env:AGENTSWARM_RECORD_PILOT_URL -eq "1") {
    python scripts/record_pilot_url.py $TargetUrl
    exit $LASTEXITCODE
}
