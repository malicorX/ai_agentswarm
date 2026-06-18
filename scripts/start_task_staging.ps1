param(
    [Parameter(Mandatory = $true)]
    [string]$GoalId
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
. "$PSScriptRoot\ensure_staging_env.ps1" -ApiUrl $ApiUrl
& "$PSScriptRoot\start_task.ps1" -GoalId $GoalId -BaseUrl $ApiUrl @args
exit $LASTEXITCODE
