# Run the full local test suite: deps, pytest, TypeScript SDK, Phase 0 e2e demo.
# Optional: -Staging hits theebie quick verify (needs bootstrap token or SSH).
param(
    [switch]$SkipDemo,
    [switch]$Staging
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== AgentSwarm: run_all_tests ===" -ForegroundColor Cyan

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1

Write-Host "Installing Python packages..."
pip install -q -e "./platform[dev]" -e "./agents" -e "./packages/sdk-python" -e "./packages/mcp-adapter[dev]" pytest

Write-Host "`n--- Python tests ---"
python -m pytest -q platform/tests agents/tests packages/mcp-adapter/tests pilot/news-hub/tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Host "`n--- TypeScript SDK ---"
    Push-Location packages/sdk-typescript
    try {
        if (-not (Test-Path node_modules)) { npm install --silent }
        npm test
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`n(skip TypeScript SDK: npm not found)" -ForegroundColor Yellow
}

if (-not $SkipDemo) {
    Write-Host "`n--- Phase 0 e2e demo ---"
    & "$PSScriptRoot\demo_phase0.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Staging) {
    Write-Host "`n--- Staging quick verify (theebie) ---"
    $HostSsh = if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }
    $EnvFile = if ($env:AGENTSWARM_PLATFORM_ENV_FILE) { $env:AGENTSWARM_PLATFORM_ENV_FILE } else { "/etc/agentswarm/platform.env" }
    if (-not $env:AGENTSWARM_BOOTSTRAP_TOKEN) {
        $boot = ssh $HostSsh "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' $EnvFile | cut -d= -f2-" 2>$null
        if ($boot) { $env:AGENTSWARM_BOOTSTRAP_TOKEN = $boot.Trim() }
    }
    if (-not $env:AGENTSWARM_BOOTSTRAP_TOKEN) {
        Write-Error "Staging requires AGENTSWARM_BOOTSTRAP_TOKEN or SSH access to $HostSsh"
    }
    $env:AGENTSWARM_EXPECT_DISPATCH = "1"
    $env:AGENTSWARM_VERIFY_QUICK = "1"
    Remove-Item Env:AGENTSWARM_VERIFY_FULL -ErrorAction SilentlyContinue
    python scripts/verify_production_staging.py https://theebie.de/agentswarm/api
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "`n=== All tests passed ===" -ForegroundColor Green
