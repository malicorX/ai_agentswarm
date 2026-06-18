# Distributed git engineering: sparky1=coordinator+tester, sparky2=codewriter, local=reviewer.
param(
    [switch]$SyncRemotes,
    [switch]$InitGitWorkspace,
    [switch]$GitInContainer,
    [string]$Sparky1Host = $(if ($env:AGENTSWARM_SPARKY1_HOST) { $env:AGENTSWARM_SPARKY1_HOST } else { "sparky1" }),
    [string]$Sparky2Host = $(if ($env:AGENTSWARM_SPARKY2_HOST) { $env:AGENTSWARM_SPARKY2_HOST } else { "sparky2" }),
    [string]$DistRepo = $(if ($env:AGENTSWARM_DIST_REPO) { $env:AGENTSWARM_DIST_REPO } else { "~/ai_agentSwarm" }),
    [string]$GitFixture = $(if ($env:AGENTSWARM_GIT_FIXTURE) { $env:AGENTSWARM_GIT_FIXTURE } else { "primes" }),
    [string]$GitRepoUrl = ""
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
    ssh $RemoteHost "mkdir -p $DistRepo/scripts $DistRepo/pilot"
    scp -r agents platform "${RemoteHost}:${DistRepo}/"
    scp -r pilot/engineering-lab "${RemoteHost}:${DistRepo}/pilot/"
    scp scripts/demo_volunteer_subjective.py scripts/run_volunteer_role.py scripts/demo_distributed_volunteers.py scripts/demo_engineering_goal.py scripts/demo_distributed_engineering_git.py "${RemoteHost}:${DistRepo}/scripts/"
    $setupCmd = "cd $DistRepo && python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q -e platform -e agents && .venv/bin/pip install -q pytest"
    ssh $RemoteHost $setupCmd
    if ($LASTEXITCODE -ne 0) {
        throw "Remote venv setup failed on $RemoteHost"
    }
    $gitCheck = ssh $RemoteHost "git --version >/dev/null 2>&1 && echo ok || echo missing"
    if ($gitCheck.Trim() -ne "ok") {
        throw "Git is required on $RemoteHost for distributed git demo"
    }
}

if ($InitGitWorkspace) {
    & "$PSScriptRoot\init_git_workspace_staging.ps1" -Fixture $GitFixture
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Resolve-GitRepoUrl {
    if ($GitRepoUrl) { return $GitRepoUrl.Trim() }
    if ($env:AGENTSWARM_GIT_REPO_URL) { return $env:AGENTSWARM_GIT_REPO_URL.Trim() }
    $fromEnv = ssh $HostSsh "grep -E '^AGENTSWARM_GIT_REPO_URL=' $EnvFile 2>/dev/null | cut -d= -f2-" 2>$null
    if ($fromEnv) {
        $trimmed = $fromEnv.Trim().Trim([char]13)
        if ($trimmed) { return $trimmed }
    }
    return "${HostSsh}:/var/lib/agentswarm/git-workspaces/${GitFixture}.git"
}

$resolvedRepoUrl = Resolve-GitRepoUrl
$env:AGENTSWARM_GIT_REPO_URL = $resolvedRepoUrl
Write-Host "Using git repo: $resolvedRepoUrl"

if (-not $env:AGENTSWARM_BOOTSTRAP_TOKEN) {
    $boot = ssh $HostSsh "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' $EnvFile | cut -d= -f2-"
    if (-not $boot) { Write-Error "Could not read AGENTSWARM_BOOTSTRAP_TOKEN" }
    $env:AGENTSWARM_BOOTSTRAP_TOKEN = $boot.Trim().Trim([char]13)
}

if (-not $env:AGENTSWARM_ASSIGNMENT_SECRET) {
    $secret = ssh $HostSsh "grep -E '^AGENTSWARM_ASSIGNMENT_SECRET=' $EnvFile | cut -d= -f2-"
    if (-not $secret) { Write-Error "Could not read AGENTSWARM_ASSIGNMENT_SECRET" }
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
        $gitRemote = (ssh $hostName "git ls-remote $($env:AGENTSWARM_GIT_REPO_URL) HEAD 2>/dev/null && echo ok || echo fail") -join "`n"
        if ($gitRemote -notmatch "\bok\b") {
            Write-Error "sparky $hostName cannot reach git repo $($env:AGENTSWARM_GIT_REPO_URL). Check SSH keys to theebie."
        }
    }
}

python scripts/demo_distributed_engineering_git.py --base-url $ApiUrl $(if ($GitInContainer) { '--git-in-container' }) @args
exit $LASTEXITCODE
