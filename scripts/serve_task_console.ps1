$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
try {
    . "$PSScriptRoot\ensure_staging_env.ps1" -ApiUrl $ApiUrl
} catch {
    Write-Warning "Could not load staging secrets via SSH: $_"
    Write-Warning "Start task will fail unless AGENTSWARM_BOOTSTRAP_TOKEN and AGENTSWARM_ASSIGNMENT_SECRET are set."
}

$env:AGENTSWARM_REPO_ROOT = $Root
$Port = if ($env:AGENTSWARM_TASK_CONSOLE_PORT) { $env:AGENTSWARM_TASK_CONSOLE_PORT } else { "8765" }

Write-Host "Task console: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "API: $ApiUrl"
Write-Host "Press Ctrl+C to stop."

& "$Root\.venv\Scripts\python.exe" -m tools.task_console.server
