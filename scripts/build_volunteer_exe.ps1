$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Use a dedicated venv so pip does not overwrite .venv\Scripts\agentswarm-volunteer.exe
# while the volunteer GUI is running from the dev environment.
$BuildVenv = Join-Path $RepoRoot ".venv-build"
$VenvPython = Join-Path $BuildVenv "Scripts\python.exe"

$runningVolunteer = Get-Process -Name "agentswarm-volunteer" -ErrorAction SilentlyContinue
if ($runningVolunteer) {
    Write-Host "Note: agentswarm-volunteer is running (dev .venv). Build uses .venv-build so that is OK." -ForegroundColor Yellow
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating build virtualenv (.venv-build)..." -ForegroundColor Cyan
    python -m venv $BuildVenv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Installing packages into .venv-build (isolated from dev .venv)..." -ForegroundColor Cyan
& $VenvPython -m pip install -q --upgrade pip
& $VenvPython -m pip install -q -e "./platform" -e "./agents" pyinstaller
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "If you see 'Zugriff verweigert' on .venv-build, close antivirus scan or retry." -ForegroundColor Yellow
    Write-Host "If the error mentions .venv\Scripts (not .venv-build), rerun with this updated script." -ForegroundColor Yellow
    exit $LASTEXITCODE
}

Write-Host "Building AgentSwarmVolunteer.exe..." -ForegroundColor Cyan
& $VenvPython -m PyInstaller --noconfirm client/AgentSwarmVolunteer.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ExePath = Join-Path $RepoRoot "dist\AgentSwarmVolunteer.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "Build failed: $ExePath not found"
}

$SizeMb = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
Write-Host ""
Write-Host "Built $ExePath - $SizeMb MB" -ForegroundColor Green
Write-Host "Friend bundle: .\scripts\build_friend_bundle.ps1"
