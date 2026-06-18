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
$deploySh = "scripts/deploy_swarm_theebie.sh"
$unixRoot = ($Root -replace '\\', '/')
if ($unixRoot -match '^([A-Za-z]):') {
    $drive = $Matches[1].ToLower()
    $gitBash = Join-Path ${env:ProgramFiles} "Git\bin\bash.exe"
    if (Test-Path $gitBash) {
        $unixRoot = "/$drive" + $unixRoot.Substring(2)
        & $gitBash -lc "cd '$unixRoot' && bash '$deploySh'"
    } else {
        $unixRoot = "/mnt/$drive" + $unixRoot.Substring(2)
        & $bash.Source -lc "cd '$unixRoot' && bash '$deploySh'"
    }
} else {
    & $bash.Source -lc "cd '$unixRoot' && bash '$deploySh'"
}
exit $LASTEXITCODE
