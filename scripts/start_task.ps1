param(
    [Parameter(Mandatory = $true)]
    [string]$GoalId,

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

if ($BaseUrl -match 'theebie\.de') {
    . "$PSScriptRoot\ensure_staging_env.ps1" -ApiUrl $BaseUrl
} elseif (-not $env:AGENTSWARM_ASSIGNMENT_SECRET) {
    Write-Warning "AGENTSWARM_ASSIGNMENT_SECRET is not set; volunteer workers may fail on dispatch submit."
}

$startCmd = Get-Command agentswarm-start-task -ErrorAction SilentlyContinue
if ($startCmd) {
    agentswarm-start-task --base-url $BaseUrl --goal-id $GoalId @args
} else {
    python -m agentswarm_agents.start_task --base-url $BaseUrl --goal-id $GoalId @args
}
exit $LASTEXITCODE
