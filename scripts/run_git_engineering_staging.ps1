# Git engineering on staging with shared bare repo on theebie.
param(
    [string]$TaskFile = "tasks/example-primes-git-distributed.txt",
    [switch]$InitGitWorkspace
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($InitGitWorkspace -or -not $env:AGENTSWARM_GIT_REPO_URL) {
    & "$PSScriptRoot\init_git_workspace_staging.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$env:AGENTSWARM_REPO_ROOT = $Root
Write-Host "workspace_mode=git repo=$($env:AGENTSWARM_GIT_REPO_URL)"
& "$PSScriptRoot\run_task_staging.ps1" -TaskFile $TaskFile
exit $LASTEXITCODE
