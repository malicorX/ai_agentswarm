# AgentSwarm volunteer worker - desktop GUI (Tkinter).
# Separate from the task console (operator web UI in the browser).
param(
    [string]$ApiUrl = "",
    [switch]$Standalone
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $ApiUrl) {
    $ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
}
try {
    . "$PSScriptRoot\ensure_staging_env.ps1" -ApiUrl $ApiUrl
} catch {
    Write-Warning "Could not load staging secrets via SSH: $_"
    Write-Warning "Volunteer submit may fail without AGENTSWARM_ASSIGNMENT_SECRET."
}

$env:AGENTSWARM_REPO_ROOT = $Root
$env:AGENTSWARM_STAGING_API_URL = $ApiUrl
$env:AGENTSWARM_PLATFORM_URL = $ApiUrl

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$DistVolunteer = Join-Path $Root "dist\AgentSwarmVolunteer.exe"

Write-Host "Starting AgentSwarm Volunteer GUI (worker)" -ForegroundColor Green
Write-Host "Platform: $ApiUrl"
Write-Host 'Task console (operator): .\scripts\serve_task_console.ps1 -Browser'

if ($Standalone -and (Test-Path $DistVolunteer)) {
    Write-Host "Using standalone build: dist\AgentSwarmVolunteer.exe" -ForegroundColor Cyan
    & $DistVolunteer
    exit $LASTEXITCODE
}

if (-not (Test-Path $Python)) {
    Write-Error "Dev .venv missing. Run: .\scripts\repair_dev_venv.ps1"
}

try {
    & $Python -c "import agentswarm_agents" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "import failed" }
} catch {
    Write-Host "Dev install broken. Run: .\scripts\repair_dev_venv.ps1" -ForegroundColor Yellow
    if (Test-Path $DistVolunteer) {
        Write-Host "Falling back to dist\AgentSwarmVolunteer.exe" -ForegroundColor Yellow
        & $DistVolunteer
        exit $LASTEXITCODE
    }
    throw
}

& $Python -m agentswarm_agents.volunteer_gui
