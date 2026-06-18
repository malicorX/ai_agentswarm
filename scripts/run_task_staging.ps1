# Create + execute a task file on staging (recommended path).
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskFile
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
. "$PSScriptRoot\ensure_staging_env.ps1" -ApiUrl $ApiUrl
$env:AGENTSWARM_REPO_ROOT = $Root

$resolvedTaskFile = $TaskFile
if (-not [System.IO.Path]::IsPathRooted($TaskFile)) {
    $resolvedTaskFile = Join-Path $Root $TaskFile
}

$startCmd = Get-Command agentswarm-start-task -ErrorAction SilentlyContinue
if ($startCmd) {
    agentswarm-start-task --base-url $ApiUrl --task-file $resolvedTaskFile
} else {
    python -m agentswarm_agents.start_task --base-url $ApiUrl --task-file $resolvedTaskFile
}
exit $LASTEXITCODE
