# Creative subjective e2e on staging with docker/qwen2.5-coder-3b (real LLM in worker container).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

. "$PSScriptRoot\ensure_staging_env.ps1"

$ModelId = if ($env:AGENTSWARM_DOCKER_MODEL_ID) { $env:AGENTSWARM_DOCKER_MODEL_ID } else { "docker/qwen2.5-coder-3b" }
$ApiUrl = $env:AGENTSWARM_STAGING_API_URL
$MinReviewers = if ($args -contains "-MinReviewers") {
    $i = [array]::IndexOf($args, "-MinReviewers")
    [int]$args[$i + 1]
} else { 1 }

Write-Host "Model: $ModelId"
Write-Host "API: $ApiUrl"
Write-Host "Ensuring worker image..."
& "$PSScriptRoot\build_worker_image.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Preparing model weights (skip if cached)..."
& "$PSScriptRoot\prepare_volunteer_model.ps1" $ModelId
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$goalTimeout = if ($env:AGENTSWARM_DOCKER_E2E_GOAL_TIMEOUT) { $env:AGENTSWARM_DOCKER_E2E_GOAL_TIMEOUT } else { "600" }
$waitSec = if ($env:AGENTSWARM_DOCKER_E2E_WAIT_SEC) { $env:AGENTSWARM_DOCKER_E2E_WAIT_SEC } else { "90" }

Write-Host "Running volunteer subjective demo (creative LLM in Docker)..."
& "$Root\.venv\Scripts\python.exe" scripts\demo_volunteer_subjective.py `
    --base-url $ApiUrl `
    --model-id $ModelId `
    --min-reviewers $MinReviewers `
    --goal-timeout-sec $goalTimeout `
    --wait-sec $waitSec `
    --isolate-dispatch
exit $LASTEXITCODE
