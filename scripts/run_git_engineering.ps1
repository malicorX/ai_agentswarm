# Run an engineering goal with git workspace handoff (D0).
param(
    [string]$TaskFile = "tasks/example-primes-git.txt"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:AGENTSWARM_REPO_ROOT = $Root

git --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Git is required for git engineering. Install Git and retry."
}

$resolvedTaskFile = $TaskFile
if (-not [System.IO.Path]::IsPathRooted($TaskFile)) {
    $resolvedTaskFile = Join-Path $Root $TaskFile
}

Write-Host "workspace_mode=git - codewriter pushes commit; tester clones workspace_ref"
& "$PSScriptRoot\run_task_staging.ps1" -TaskFile $resolvedTaskFile
exit $LASTEXITCODE
