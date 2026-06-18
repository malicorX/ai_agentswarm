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
try {
    Copy-Item -Force $Exe $OutExe
} catch {
    Write-Warning "Could not copy to dist (close the running app first). Built exe: $Exe"
    exit 0
}

Write-Host ""
Write-Host "Built: $OutExe" -ForegroundColor Green
Write-Host "Run:   .\scripts\start_task_console_app.ps1"
