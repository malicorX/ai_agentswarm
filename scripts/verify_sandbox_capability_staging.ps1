# Verify sandbox capabilities are registered on staging (run after deploy_platform_theebie.ps1).
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\ensure_staging_env.ps1"

$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
$headers = @{ "X-Bootstrap-Token" = $env:AGENTSWARM_BOOTSTRAP_TOKEN }

$response = Invoke-RestMethod -Uri "$ApiUrl/capabilities" -Headers $headers
$ids = @($response.capabilities | ForEach-Object { $_.id })

$required = @("sandbox.build", "sandbox.test")
$missing = @($required | Where-Object { $ids -notcontains $_ })
if ($missing.Count -gt 0) {
    Write-Host "FAIL: missing sandbox capabilities: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Registered: $($ids -join ', ')"
    Write-Host "Redeploy: .\scripts\deploy_platform_theebie.ps1"
    exit 1
}

foreach ($capId in $required) {
    $cap = $response.capabilities | Where-Object { $_.id -eq $capId } | Select-Object -First 1
    $tasks = @($cap.task_types)
    $expected = if ($capId -eq "sandbox.build") { "builder.compile" } else { "tester.run" }
    if ($tasks -notcontains $expected) {
        Write-Host "FAIL: $capId missing task type $expected" -ForegroundColor Red
        Write-Host "Task types: $($tasks -join ', ')"
        exit 1
    }
}

if ($ids -contains "sandbox.linux") {
    Write-Host "OK: sandbox.build + sandbox.test registered (legacy sandbox.linux present)"
} else {
    Write-Host "OK: sandbox.build + sandbox.test registered"
}
exit 0
