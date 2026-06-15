$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Tag = if ($env:AGENTSWARM_WORKER_IMAGE) { $env:AGENTSWARM_WORKER_IMAGE } else { "agentswarm-worker:dev" }

Write-Host "Building worker image: $Tag"
docker build -f docker/worker/Dockerfile -t $Tag .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Smoke test: creative.text capsule"
$input = '{"task_type":"creative.text","capsule":{"brief":"smoke test"}}'
$result = $input | docker run --rm -i --network none $Tag
Write-Host $result
if ($result -notmatch "Container poem") {
    Write-Error "Smoke test failed: unexpected worker output"
}
Write-Host "Worker image ready: $Tag"
