# Seed shared bare git workspace on theebie and print AGENTSWARM_GIT_REPO_URL.
param(
    [string]$HostSsh = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$Fixture = $(if ($env:AGENTSWARM_GIT_FIXTURE) { $env:AGENTSWARM_GIT_FIXTURE } else { "primes" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$remoteScript = Join-Path $Root "scripts\remote\init_git_workspace_theebie.sh"
if (-not (Test-Path $remoteScript)) {
    Write-Error "Missing $remoteScript"
}

Write-Host "Seeding git workspace on $HostSsh (fixture=$Fixture) ..."
$remotePath = if ($env:AGENTSWARM_PLATFORM_REMOTE_DIR) { "$($env:AGENTSWARM_PLATFORM_REMOTE_DIR)/scripts/remote/init_git_workspace_theebie.sh" } else { "/opt/agentswarm/scripts/remote/init_git_workspace_theebie.sh" }
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $output = @(ssh $HostSsh "AGENTSWARM_GIT_FIXTURE='$Fixture' bash '$remotePath'" 2>&1)
} finally {
    $ErrorActionPreference = $prevEap
}
$output | ForEach-Object { Write-Host $_ }

$repoLine = $output | Where-Object { $_ -match '^AGENTSWARM_GIT_REPO_URL=' } | Select-Object -First 1
if (-not $repoLine) {
    Write-Error "Remote init did not print AGENTSWARM_GIT_REPO_URL"
}

$repoUrl = ($repoLine -split '=', 2)[1].Trim()
$env:AGENTSWARM_GIT_REPO_URL = $repoUrl
Write-Host ""
Write-Host "Set for this session: `$env:AGENTSWARM_GIT_REPO_URL = $repoUrl"
Write-Host "Verify from sparky: git ls-remote $repoUrl HEAD"
