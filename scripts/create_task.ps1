# Enqueue a task file on the platform (no volunteer workers started).
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskFile,

    [string]$BaseUrl = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $BaseUrl) {
    if ($env:AGENTSWARM_STAGING_API_URL) {
        $BaseUrl = $env:AGENTSWARM_STAGING_API_URL
    } elseif ($env:AGENTSWARM_PLATFORM_URL) {
        $BaseUrl = $env:AGENTSWARM_PLATFORM_URL
    } else {
        $BaseUrl = "http://127.0.0.1:8000"
    }
}

$resolvedTaskFile = $TaskFile
if (-not [System.IO.Path]::IsPathRooted($TaskFile)) {
    $resolvedTaskFile = Join-Path $Root $TaskFile
}
if (-not (Test-Path -LiteralPath $resolvedTaskFile)) {
    Write-Error "Task file not found: $resolvedTaskFile"
}

$createCmd = Get-Command agentswarm-create-task -ErrorAction SilentlyContinue
if ($createCmd) {
    agentswarm-create-task --base-url $BaseUrl --task-file $resolvedTaskFile
} else {
    python -m agentswarm_agents.create_task --base-url $BaseUrl --task-file $resolvedTaskFile
}
exit $LASTEXITCODE
