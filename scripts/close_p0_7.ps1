param(
    [string]$Url = "https://malicorx.github.io/ai_agentswarm"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
python scripts/close_p0_7.py $Url
exit $LASTEXITCODE
