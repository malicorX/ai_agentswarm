# Phase 13 close-out: scoped idle redispatch + subjective verify on staging (P13.11).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pytest -q platform/tests agents/tests

$HostSsh = if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }
$EnvFile = if ($env:AGENTSWARM_PLATFORM_ENV_FILE) { $env:AGENTSWARM_PLATFORM_ENV_FILE } else { "/etc/agentswarm/platform.env" }
$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }

if (-not $env:AGENTSWARM_BOOTSTRAP_TOKEN) {
    $boot = ssh $HostSsh "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' $EnvFile | cut -d= -f2-"
    if (-not $boot) {
        Write-Error "Could not read AGENTSWARM_BOOTSTRAP_TOKEN from ${HostSsh}:${EnvFile}"
    }
    $env:AGENTSWARM_BOOTSTRAP_TOKEN = $boot.Trim()
}

if (-not $env:AGENTSWARM_ASSIGNMENT_SECRET) {
    $secret = ssh $HostSsh "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' $EnvFile | cut -d= -f2-"
    if (-not $secret) {
        Write-Error "Could not read AGENTSWARM_ASSIGNMENT_SECRET from ${HostSsh}:${EnvFile}"
    }
    $env:AGENTSWARM_ASSIGNMENT_SECRET = $secret.Trim()
}

$env:AGENTSWARM_EXPECT_DISPATCH = "1"
python scripts/verify_dispatch_staging.py $ApiUrl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:AGENTSWARM_EXPECT_HARDWARE_GATES = "1"
python scripts/verify_hardware_gates_staging.py $ApiUrl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:AGENTSWARM_EXPECT_LEASE_RECLAIM = "1"
python scripts/verify_lease_reclaim_staging.py $ApiUrl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:AGENTSWARM_VERIFY_SUBJECTIVE_MIN_REVIEWERS = "1"
if ($env:AGENTSWARM_VERIFY_SKIP_PREP -ne "1") {
    powershell -File scripts/prep_staging_subjective_verify.ps1
}
$subjectiveOk = $false
foreach ($attempt in 1, 2, 3, 4, 5) {
    python scripts/verify_volunteer_subjective_staging.py $ApiUrl
    if ($LASTEXITCODE -eq 0) {
        $subjectiveOk = $true
        break
    }
    if ($attempt -lt 5) {
        Write-Host "Subjective verify attempt $attempt failed; retrying in 15s..." -ForegroundColor Yellow
        Start-Sleep -Seconds 15
    }
}
if (-not $subjectiveOk) { exit 1 }

Write-Host "Phase 13 close-out checks OK. Tag with:"
Write-Host "  git tag v0.14.0-phase13 && git push origin v0.14.0-phase13"
