$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$AppDir = Join-Path $Root "apps\agentswarm-task-console"
if (-not (Test-Path $AppDir)) {
    Write-Error "Native app sources not found at $AppDir"
}

Write-Host "Building AgentSwarm Task Console (release)..." -ForegroundColor Cyan
Push-Location $AppDir
try {
    cargo build --release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

$Exe = Join-Path $AppDir "target\release\agentswarm-task-console.exe"
if (-not (Test-Path $Exe)) {
    Write-Error "Build succeeded but executable missing: $Exe"
}

$OutDir = Join-Path $Root "dist"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutExe = Join-Path $OutDir "agentswarm-task-console.exe"
$running = Get-Process -Name "agentswarm-task-console" -ErrorAction SilentlyContinue
if ($running) {
    Write-Host ""
    Write-Host "agentswarm-task-console is running (close the window first to update dist\)." -ForegroundColor Yellow
    foreach ($proc in $running) {
        Write-Host "  PID $($proc.Id)" -ForegroundColor Yellow
    }
}
try {
    Copy-Item -Force $Exe $OutExe
} catch {
    Write-Warning "Could not copy to dist (file in use). Fresh build is still at:"
    Write-Host "  $Exe" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Close the task console, then rerun: .\scripts\build_task_console_app.ps1" -ForegroundColor Yellow
    exit 0
}

$Launcher = Join-Path $OutDir "TaskConsole.cmd"
@"
@echo off
setlocal
cd /d "%~dp0.."
set "AGENTSWARM_REPO_ROOT=%CD%"
start "" "%~dp0agentswarm-task-console.exe"
"@ | Set-Content -Encoding ASCII -Path $Launcher

Write-Host ""
Write-Host "Built: $OutExe" -ForegroundColor Green
Write-Host "Run:   .\dist\TaskConsole.cmd"
Write-Host "   or: .\scripts\start_task_console_app.ps1"
