$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
try {
    . "$PSScriptRoot\ensure_staging_env.ps1" -ApiUrl $ApiUrl
} catch {
    Write-Warning "Could not load staging secrets via SSH: $_"
}

$env:AGENTSWARM_REPO_ROOT = $Root

$Candidates = @(
    (Join-Path $Root "dist\agentswarm-task-console.exe"),
    (Join-Path $Root "apps\agentswarm-task-console\target\release\agentswarm-task-console.exe")
)

$Exe = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Exe) {
    Write-Host "Native app not built yet. Run: .\scripts\build_task_console_app.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting $Exe" -ForegroundColor Green
Write-Host "Close any old task console browser tabs or python servers on ports 8765-8785 if startup fails."
Push-Location $Root
try {
    & $Exe
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
