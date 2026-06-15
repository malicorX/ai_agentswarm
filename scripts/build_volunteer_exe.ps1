$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "Installing editable packages..."
python -m pip install -e platform -e agents pyinstaller

Write-Host "Building AgentSwarmVolunteer.exe..."
pyinstaller --noconfirm client/AgentSwarmVolunteer.spec

$ExePath = Join-Path $RepoRoot "dist/AgentSwarmVolunteer.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "Build failed: $ExePath not found"
}

Write-Host "Built $ExePath"
Write-Host "Manual install: copy dist/AgentSwarmVolunteer.exe to your machine (signing not included)."
