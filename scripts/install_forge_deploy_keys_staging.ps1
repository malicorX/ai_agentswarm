# Install per-goal forge public keys on theebie for git SSH (requires AGENTSWARM_FORGE_MINT_KEYS=1).
# When AGENTSWARM_FORGE_AUTO_INSTALL_KEYS=1 on the platform, new goals install keys automatically;
# run this script to backfill credentials minted before auto-install was enabled.
param(
    [string]$HostSsh = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$DbPath = $(if ($env:AGENTSWARM_DB) { $env:AGENTSWARM_DB } else { "/var/lib/agentswarm/agentswarm.db" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$remoteScript = Join-Path $Root "scripts\remote\install_forge_deploy_keys_theebie.sh"
if (-not (Test-Path $remoteScript)) {
    Write-Error "Missing $remoteScript"
}

Write-Host "Installing forge deploy keys on $HostSsh ..."
$remotePath = if ($env:AGENTSWARM_PLATFORM_REMOTE_DIR) { "$($env:AGENTSWARM_PLATFORM_REMOTE_DIR)/scripts/remote/install_forge_deploy_keys_theebie.sh" } else { "/opt/agentswarm/scripts/remote/install_forge_deploy_keys_theebie.sh" }
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $output = @(ssh $HostSsh "AGENTSWARM_DB='$DbPath' bash '$remotePath'" 2>&1)
} finally {
    $ErrorActionPreference = $prevEap
}
$output | ForEach-Object { Write-Host $_ }
