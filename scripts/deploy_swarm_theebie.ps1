param(
    [string]$TheebieHost = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$RemoteRoot = $(if ($env:AGENTSWARM_INSTALL_ROOT) { $env:AGENTSWARM_INSTALL_ROOT } else { "/opt/agentswarm" }),
    [string]$PlatformUrl = $(if ($env:AGENTSWARM_PLATFORM_URL) { $env:AGENTSWARM_PLATFORM_URL } elseif ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }),
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:AGENTSWARM_THEEBIE_HOST = $TheebieHost
$env:AGENTSWARM_INSTALL_ROOT = $RemoteRoot
$env:AGENTSWARM_PLATFORM_URL = $PlatformUrl
if ($SkipVerify) { $env:AGENTSWARM_VERIFY_PRODUCTION_SWARM = "0" }

$bash = Get-Command bash -ErrorAction SilentlyContinue
if (-not $bash) {
    Write-Error "bash is required (Git Bash or WSL)."
}
& $bash.Source (Join-Path $Root "scripts\deploy_swarm_theebie.sh")
exit $LASTEXITCODE
