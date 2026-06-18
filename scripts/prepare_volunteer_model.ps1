$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ModelId = if ($args.Count -gt 0) { $args[0] } else { "docker/qwen2.5-coder-3b" }

Write-Host "Preparing model: $ModelId"
Write-Host "Data dir: $env:LOCALAPPDATA\AgentSwarm (override with AGENTSWARM_CLIENT_DATA_DIR)"

& "$Root\.venv\Scripts\python.exe" -m agentswarm_agents.volunteer_gui --prepare-only --model-id $ModelId
exit $LASTEXITCODE
