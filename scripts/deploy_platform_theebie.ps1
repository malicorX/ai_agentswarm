param(
    [string]$TheebieHost = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$RemoteRoot = $(if ($env:AGENTSWARM_PLATFORM_REMOTE_DIR) { $env:AGENTSWARM_PLATFORM_REMOTE_DIR } else { "/opt/agentswarm" }),
    [string]$ApiUrl = $(if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }),
    [switch]$SkipVerify,
    [switch]$RecordUrl
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:AGENTSWARM_THEEBIE_HOST = $TheebieHost
$env:AGENTSWARM_PLATFORM_REMOTE_DIR = $RemoteRoot
$env:AGENTSWARM_STAGING_API_URL = $ApiUrl
if ($SkipVerify) { $env:AGENTSWARM_VERIFY_STAGING_API = "0" }
if ($RecordUrl -or $env:AGENTSWARM_RECORD_STAGING_API_URL -eq "1") {
    $env:AGENTSWARM_RECORD_STAGING_API_URL = "1"
}

$bash = Get-Command bash -ErrorAction SilentlyContinue
if (-not $bash) {
    Write-Error "bash is required (Git Bash or WSL). Run scripts/deploy_platform_theebie.sh directly."
}
& $bash.Source (Join-Path $Root "scripts\deploy_platform_theebie.sh")
exit $LASTEXITCODE
