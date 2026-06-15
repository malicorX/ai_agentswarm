param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
pip install -q -e "./platform[dev]" -e "./agents" -e "./packages/sdk-python" pytest

$env:AGENTSWARM_REPO_ROOT = $RepoRoot
$env:AGENTSWARM_DB = Join-Path $RepoRoot "platform\data\deploy-demo.db"
$env:AGENTSWARM_PLATFORM_URL = "http://127.0.0.1:8000"
$env:AGENTSWARM_AUTH_DISABLED = "1"
$env:AGENTSWARM_CREDIBILITY_ENABLED = "1"
$env:AGENTSWARM_CRED_INITIAL = "60"

if (Test-Path $env:AGENTSWARM_DB) { Remove-Item $env:AGENTSWARM_DB -Force }

$platformJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    $env:AGENTSWARM_DB = Join-Path $root "platform\data\deploy-demo.db"
    $env:AGENTSWARM_AUTH_DISABLED = "1"
    $env:AGENTSWARM_CREDIBILITY_ENABLED = "1"
    $env:AGENTSWARM_CRED_INITIAL = "60"
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

    Write-Host "Platform ready. Running deploy sign-off demo..."
    python -m agentswarm_agents.deploy_demo

    Write-Host "Running deploy demo tests..."
    python -m pytest -q agents/tests/test_deploy_demo.py platform/tests/test_deploy_signoff.py

    Write-Host "demo_deploy_signoff.ps1 complete"
}
finally {
    Stop-Job $platformJob -ErrorAction SilentlyContinue
    Remove-Job $platformJob -Force -ErrorAction SilentlyContinue
}
