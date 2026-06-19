# Start the native AgentSwarm Task Console (desktop window with embedded UI).
param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
try {
    . "$PSScriptRoot\ensure_staging_env.ps1" -ApiUrl $ApiUrl
} catch {
    Write-Warning "Could not load staging secrets via SSH: $_"
    Write-Warning "Dispatch may fail without AGENTSWARM_BOOTSTRAP_TOKEN."
}

$env:AGENTSWARM_REPO_ROOT = $Root
$env:AGENTSWARM_STAGING_API_URL = $ApiUrl
$env:AGENTSWARM_PLATFORM_URL = $ApiUrl

$Candidates = @(
    (Join-Path $Root "dist\agentswarm-task-console.exe"),
    (Join-Path $Root "apps\agentswarm-task-console\target\release\agentswarm-task-console.exe")
)

$Exe = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Exe -or $Build) {
    Write-Host "Building native task console (first run may take a few minutes)..." -ForegroundColor Cyan
    & "$PSScriptRoot\build_task_console_app.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $Exe = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Exe) {
    Write-Error "Native app executable not found after build."
}

Write-Host ""
Write-Host "Starting AgentSwarm Task Console (native window)" -ForegroundColor Green
Write-Host "API: $ApiUrl"
Write-Host "If the window fails to open, use: .\scripts\serve_task_console.ps1 -Browser"
Write-Host "Close other task-console windows first (avoids WebView port conflicts)."
Write-Host ""

& $Exe
exit $LASTEXITCODE
