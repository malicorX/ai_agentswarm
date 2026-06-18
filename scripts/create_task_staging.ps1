param(
    [Parameter(Mandatory = $true)]
    [string]$TaskFile
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
. "$PSScriptRoot\ensure_staging_env.ps1" -ApiUrl $ApiUrl
& "$PSScriptRoot\create_task.ps1" -TaskFile $TaskFile -BaseUrl $ApiUrl
exit $LASTEXITCODE
