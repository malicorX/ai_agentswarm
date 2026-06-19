# Repair dev .venv after a failed pip install (e.g. WinError 5 on agentswarm-volunteer.exe).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Creating .venv ..." -ForegroundColor Cyan
    python -m venv .venv
}

$Broken = Join-Path $Root ".venv\Lib\site-packages\~gentswarm_agents-0.3.0.dist-info"
if (Test-Path $Broken) {
    Write-Host "Removing broken agents install: $Broken" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $Broken
}

Write-Host "Reinstalling platform + agents into .venv ..." -ForegroundColor Cyan
& $Python -m pip install -q --upgrade pip
& $Python -m pip install -e "./platform" -e "./agents"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "If pip fails on agentswarm-volunteer.exe, stop the volunteer GUI and rerun this script." -ForegroundColor Yellow
    exit $LASTEXITCODE
}

& $Python -c "import agentswarm_agents; print('agentswarm_agents OK')"
Write-Host ""
Write-Host "Dev .venv repaired. Start volunteer with: .\scripts\start_volunteer.ps1" -ForegroundColor Green
Write-Host "Task console (browser): .\scripts\serve_task_console.ps1 -Browser" -ForegroundColor Green
