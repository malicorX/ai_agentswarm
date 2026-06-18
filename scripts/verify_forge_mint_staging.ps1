# Verify forge mint + deploy key install on staging (D1).
param(
    [string]$HostSsh = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$ApiUrl = $(if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
. "$PSScriptRoot\ensure_staging_env.ps1"

$failures = @()

$mint = ssh $HostSsh "grep '^AGENTSWARM_FORGE_MINT_KEYS=' /etc/agentswarm/platform.env 2>/dev/null || true"
if ($mint -notmatch "=1") {
    $failures += "AGENTSWARM_FORGE_MINT_KEYS not enabled (run .\scripts\enable_forge_mint_staging.ps1)"
} else {
    Write-Host "OK: forge mint enabled"
}

Write-Host "Creating ephemeral git engineering goal to mint forge key ..."
if (-not $env:AGENTSWARM_GIT_REPO_URL) {
    $env:AGENTSWARM_GIT_REPO_URL = "root@theebie.de:/var/lib/agentswarm/git-workspaces/primes.git"
}
$env:AGENTSWARM_REPO_ROOT = $Root
$goalId = (python -c "import os,sys; from pathlib import Path; sys.path.insert(0,str(Path('agents/src').resolve())); sys.path.insert(0,str(Path('platform/src').resolve())); from agentswarm_agents.create_task import create_goal_from_spec; from agentswarm_agents.task_file import parse_task_text; spec=parse_task_text('---\ngoal_kind: engineering\nfixture: primes\nworkspace_mode: git\n---\nForge mint probe.'); print(create_goal_from_spec(os.environ['AGENTSWARM_STAGING_API_URL'], spec)['goal_id'])").Trim()
if (-not $goalId) { $failures += "could not create probe goal" }
else { Write-Host "Probe goal: $goalId" }

$checkScript = @"
import sqlite3
conn = sqlite3.connect('/var/lib/agentswarm/agentswarm.db')
row = conn.execute(
    'SELECT COUNT(1) FROM goal_forge_credentials WHERE goal_id=? AND public_key_openssh IS NOT NULL',
    ('$goalId',),
).fetchone()
print(row[0])
"@
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$keyCount = ($checkScript | ssh $HostSsh "python3 -" 2>&1) -join "`n"
$ErrorActionPreference = $prevEap
if ([int]$keyCount.Trim() -lt 1) {
    $failures += "forge credential missing public_key for $goalId"
} else {
    Write-Host "OK: forge key minted in platform DB"
}

$credScript = @"
import sqlite3
conn = sqlite3.connect('/var/lib/agentswarm/agentswarm.db')
row = conn.execute(
    'SELECT credential_id FROM goal_forge_credentials WHERE goal_id=? AND revoked_at IS NULL',
    ('$goalId',),
).fetchone()
print(row[0] if row else '')
"@
$credentialId = (($credScript | ssh $HostSsh "python3 -" 2>&1) -join "`n").Trim()

$autoInstall = ssh $HostSsh "grep '^AGENTSWARM_FORGE_AUTO_INSTALL_KEYS=' /etc/agentswarm/platform.env 2>/dev/null || true"
$autoEnabled = $autoInstall -match "=1"
if ($autoEnabled) {
    Write-Host "OK: forge auto-install enabled"
    if (-not $credentialId) {
        $failures += "missing credential_id for probe goal $goalId"
    } else {
        $marker = "agentswarm-forge:$credentialId"
        $hasMarker = ssh $HostSsh "grep -F '$marker' /root/.ssh/authorized_keys >/dev/null 2>&1 && echo yes || echo no"
        if ($hasMarker.Trim() -ne "yes") {
            $failures += "auto-install did not add authorized_keys marker for $credentialId"
        } else {
            Write-Host "OK: authorized_keys marker present for $credentialId (auto-install)"
        }
    }
} else {
    Write-Host "Auto-install off; running manual install script ..."
    & "$PSScriptRoot\install_forge_deploy_keys_staging.ps1" | Out-Host
}
$installed = ssh $HostSsh "grep -c 'agentswarm-forge:' /root/.ssh/authorized_keys 2>/dev/null || echo 0"
if ([int]$installed.Trim() -lt 1) {
    $failures += "no forge markers in authorized_keys"
} else {
    Write-Host "OK: $($installed.Trim()) forge marker(s) in authorized_keys"
}

if ($failures.Count -gt 0) {
    Write-Host "Forge verify FAILED:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
Write-Host "Forge mint staging verify OK."
exit 0
