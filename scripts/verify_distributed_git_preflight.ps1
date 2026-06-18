# Preflight for distributed git engineering demo (sparky1 + sparky2 + theebie).
param(
    [string]$Sparky1Host = $(if ($env:AGENTSWARM_SPARKY1_HOST) { $env:AGENTSWARM_SPARKY1_HOST } else { "sparky1" }),
    [string]$Sparky2Host = $(if ($env:AGENTSWARM_SPARKY2_HOST) { $env:AGENTSWARM_SPARKY2_HOST } else { "sparky2" }),
    [string]$HostSsh = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$ApiUrl = $(if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

. "$PSScriptRoot\ensure_staging_env.ps1"

$failures = @()

function Test-SshHost {
    param([string]$Name)
    $out = ssh -o BatchMode=yes -o ConnectTimeout=8 $Name "echo ok" 2>&1
    if ($LASTEXITCODE -ne 0 -or ($out -join " ").Trim() -ne "ok") {
        $script:failures += "SSH to $Name failed"
    } else {
        Write-Host "OK: SSH $Name"
    }
}

Write-Host "Checking staging API..."
try {
    $health = Invoke-RestMethod -Uri "$ApiUrl/health"
    if ($health.status -ne "ok") { $failures += "API health not ok" }
    else { Write-Host "OK: API health" }
} catch {
    $failures += "API health: $_"
}

& "$PSScriptRoot\verify_sandbox_capability_staging.ps1" 2>$null
if ($LASTEXITCODE -ne 0) {
    $caps = Invoke-RestMethod -Uri "$ApiUrl/capabilities" -Headers @{ "X-Bootstrap-Token" = $env:AGENTSWARM_BOOTSTRAP_TOKEN }
    $ids = @($caps.capabilities | ForEach-Object { $_.id })
    if ($ids -notcontains "sandbox.linux") {
        $failures += "sandbox.linux missing (run deploy_platform_theebie.ps1)"
    }
}

Test-SshHost $HostSsh
Test-SshHost $Sparky1Host
Test-SshHost $Sparky2Host

if (-not $env:AGENTSWARM_GIT_REPO_URL) {
    $fixture = if ($env:AGENTSWARM_GIT_FIXTURE) { $env:AGENTSWARM_GIT_FIXTURE } else { "primes" }
    $env:AGENTSWARM_GIT_REPO_URL = "${HostSsh}:/var/lib/agentswarm/git-workspaces/${fixture}.git"
    Write-Host "AGENTSWARM_GIT_REPO_URL not set; defaulting to $($env:AGENTSWARM_GIT_REPO_URL)"
}
$repo = $env:AGENTSWARM_GIT_REPO_URL
Write-Host "Checking git repo: $repo"
foreach ($hostName in @($Sparky1Host, $Sparky2Host)) {
    $check = (ssh $hostName "git ls-remote $repo HEAD 2>/dev/null && echo ok || echo fail") -join "`n"
    if ($check -notmatch "\bok\b") {
        Write-Host "Hint: run .\scripts\setup_sparky_git_ssh.ps1 (host key trust to theebie)"
        $failures += "sparky $hostName cannot reach git repo"
    } else {
        Write-Host "OK: $hostName git ls-remote"
    }
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "Preflight FAILED:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  - $_" }
    exit 1
}

Write-Host ""
Write-Host "Preflight OK. Run: .\scripts\demo_distributed_engineering_git.ps1"
Write-Host "Optional: .\scripts\verify_forge_mint_staging.ps1 (D1 deploy keys)"
exit 0
