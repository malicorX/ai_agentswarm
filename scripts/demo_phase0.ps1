param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
pip install -q -e "./platform[dev]" -e "./agents" pytest

$env:AGENTSWARM_REPO_ROOT = $RepoRoot
$env:AGENTSWARM_DB = Join-Path $RepoRoot "platform\data\demo.db"
$env:AGENTSWARM_PLATFORM_URL = "http://127.0.0.1:8000"
$env:AGENTSWARM_AUTH_DISABLED = "1"

if (Test-Path $env:AGENTSWARM_DB) { Remove-Item $env:AGENTSWARM_DB -Force }

$platformJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    & "$root\.venv\Scripts\python.exe" -m uvicorn agentswarm_platform.main:app --app-dir "$root\platform\src" --host 127.0.0.1 --port 8000
} -ArgumentList $RepoRoot

try {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $r = Invoke-RestMethod -Uri "$env:AGENTSWARM_PLATFORM_URL/health" -TimeoutSec 2
            if ($r.status -eq "ok") { break }
        } catch {}
        if ((Get-Date) -gt $deadline) { throw "Platform failed to start" }
        Start-Sleep -Milliseconds 500
    } while ($true)

    Write-Host "Platform ready. Running phase 0 demo..."
    python -m agentswarm_agents.demo

    Write-Host "Running platform tests..."
    Push-Location platform
    python -m pytest -q
    Pop-Location

    Write-Host "demo_phase0.ps1 complete"
}
finally {
    Stop-Job $platformJob -ErrorAction SilentlyContinue
    Remove-Job $platformJob -Force -ErrorAction SilentlyContinue
}
