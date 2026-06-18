# Run an engineering goal with Docker sandbox testing (D2).
# Requires: Docker Desktop, pip install -e platform -e agents, staging secrets.
param(
    [string]$TaskFile = "tasks/example-primes-sandbox.txt"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:AGENTSWARM_SANDBOX = "1"
$env:AGENTSWARM_REPO_ROOT = $Root

docker version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker is required for sandbox engineering. Install Docker Desktop and retry."
}

Write-Host "Building sandbox test image if needed (agentswarm/sandbox-pytest:3.12)..."
python -c "from agentswarm_agents.sandbox_executor import ensure_sandbox_test_image; ensure_sandbox_test_image()"

$resolvedTaskFile = $TaskFile
if (-not [System.IO.Path]::IsPathRooted($TaskFile)) {
    $resolvedTaskFile = Join-Path $Root $TaskFile
}

Write-Host "Sandbox workers register sandbox.build + sandbox.test (legacy AGENTSWARM_SANDBOX=1 still enables both roles)"
& "$PSScriptRoot\run_task_staging.ps1" -TaskFile $resolvedTaskFile
exit $LASTEXITCODE
