param(
    [string]$TheebieHost = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$RemoteRoot = $(if ($env:AGENTSWARM_PLATFORM_REMOTE_DIR) { $env:AGENTSWARM_PLATFORM_REMOTE_DIR } else { "/opt/agentswarm" }),
    [string]$ApiUrl = $(if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }),
    [switch]$SkipVerify,
    [switch]$RecordUrl,
    [switch]$VerifyDeployFromGoal,
    [switch]$VerifyDeployE2E
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:AGENTSWARM_THEEBIE_HOST = $TheebieHost
$env:AGENTSWARM_PLATFORM_REMOTE_DIR = $RemoteRoot
$env:AGENTSWARM_STAGING_API_URL = $ApiUrl
if ($SkipVerify) { $env:AGENTSWARM_VERIFY_STAGING_API = "0" }
if ($VerifyDeployFromGoal) { $env:AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL = "1" }
if ($VerifyDeployE2E) {
    $env:AGENTSWARM_VERIFY_DEPLOY_FROM_GOAL = "1"
    $env:AGENTSWARM_VERIFY_DEPLOY_E2E_ENGINEERING = "1"
    $env:AGENTSWARM_VERIFY_DEPLOY_SIGNOFF_CHAIN = "1"
}
if ($RecordUrl -or $env:AGENTSWARM_RECORD_STAGING_API_URL -eq "1") {
    $env:AGENTSWARM_RECORD_STAGING_API_URL = "1"
}

$bash = Get-Command bash -ErrorAction SilentlyContinue
if (-not $bash) {
    Write-Error "bash is required (Git Bash or WSL). Run scripts/deploy_platform_theebie.sh directly."
}
$deploySh = "scripts/deploy_platform_theebie.sh"
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
