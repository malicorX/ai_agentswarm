# Distributed volunteer demo: sparky1 + sparky2 + this machine against staging.
param(
    [switch]$SyncRemotes,
    [string]$Sparky1Host = $(if ($env:AGENTSWARM_SPARKY1_HOST) { $env:AGENTSWARM_SPARKY1_HOST } else { "sparky1" }),
    [string]$Sparky2Host = $(if ($env:AGENTSWARM_SPARKY2_HOST) { $env:AGENTSWARM_SPARKY2_HOST } else { "sparky2" }),
    [string]$DistRepo = $(if ($env:AGENTSWARM_DIST_REPO) { $env:AGENTSWARM_DIST_REPO } else { "~/ai_agentSwarm" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$HostSsh = if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }
$EnvFile = if ($env:AGENTSWARM_PLATFORM_ENV_FILE) { $env:AGENTSWARM_PLATFORM_ENV_FILE } else { "/etc/agentswarm/platform.env" }
$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }

function Sync-RemoteRepo {
    param([string]$RemoteHost)
    Write-Host "Syncing repo to ${RemoteHost}:${DistRepo} ..."
    ssh $RemoteHost "mkdir -p $DistRepo/scripts"
    scp -r agents platform "${RemoteHost}:${DistRepo}/"
    scp scripts/demo_volunteer_subjective.py scripts/run_volunteer_role.py scripts/demo_distributed_volunteers.py "${RemoteHost}:${DistRepo}/scripts/"
    $setupCmd = "cd $DistRepo && python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q -e platform -e agents"
    ssh $RemoteHost $setupCmd
    if ($LASTEXITCODE -ne 0) {
        throw "Remote venv setup failed on $RemoteHost"
    }
}

if (-not $env:AGENTSWARM_BOOTSTRAP_TOKEN) {
    $boot = ssh $HostSsh "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' $EnvFile | cut -d= -f2-"
    if (-not $boot) {
        Write-Error "Could not read AGENTSWARM_BOOTSTRAP_TOKEN from ${HostSsh}:${EnvFile}"
    }
    $env:AGENTSWARM_BOOTSTRAP_TOKEN = $boot.Trim().Trim([char]13)
}

if (-not $env:AGENTSWARM_ASSIGNMENT_SECRET) {
    $secret = ssh $HostSsh "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' $EnvFile | cut -d= -f2-"
    if (-not $secret) {
        Write-Error "Could not read AGENTSWARM_ASSIGNMENT_SECRET from ${HostSsh}:${EnvFile}"
    }
    $env:AGENTSWARM_ASSIGNMENT_SECRET = $secret.Trim().Trim([char]13)
}

$env:AGENTSWARM_SPARKY1_HOST = $Sparky1Host
$env:AGENTSWARM_SPARKY2_HOST = $Sparky2Host
$env:AGENTSWARM_DIST_REPO = $DistRepo
$env:AGENTSWARM_STAGING_API_URL = $ApiUrl

if ($SyncRemotes) {
    Sync-RemoteRepo -RemoteHost $Sparky1Host
    Sync-RemoteRepo -RemoteHost $Sparky2Host
} else {
    foreach ($hostName in @($Sparky1Host, $Sparky2Host)) {
        $check = ssh $hostName "test -x $DistRepo/.venv/bin/python && echo ok || echo missing"
        if ($check.Trim() -ne "ok") {
            Write-Error "Remote venv missing on ${hostName}:${DistRepo}. Re-run with -SyncRemotes."
        }
    }
}

python scripts/demo_distributed_volunteers.py --base-url $ApiUrl @args
exit $LASTEXITCODE
