# Enable model allowlist enforcement on theebie.de and verify from maintainer machine.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$HostSsh = if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }
$RemoteRoot = if ($env:AGENTSWARM_PLATFORM_REMOTE_DIR) { $env:AGENTSWARM_PLATFORM_REMOTE_DIR } else { "/opt/agentswarm" }
$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
$EnvFile = if ($env:AGENTSWARM_PLATFORM_ENV_FILE) { $env:AGENTSWARM_PLATFORM_ENV_FILE } else { "/etc/agentswarm/platform.env" }

ssh $HostSsh "mkdir -p '$RemoteRoot/scripts/remote'"
scp scripts/remote/harden_platform_model_allowlist_theebie.sh "${HostSsh}:${RemoteRoot}/scripts/remote/"
ssh $HostSsh "chmod +x '$RemoteRoot/scripts/remote/harden_platform_model_allowlist_theebie.sh' && bash '$RemoteRoot/scripts/remote/harden_platform_model_allowlist_theebie.sh'"

$boot = ssh $HostSsh "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' $EnvFile | cut -d= -f2-"
if (-not $boot) {
    Write-Error "Could not read AGENTSWARM_BOOTSTRAP_TOKEN from ${HostSsh}:${EnvFile}"
}
$env:AGENTSWARM_BOOTSTRAP_TOKEN = $boot.Trim()
$env:AGENTSWARM_EXPECT_MODEL_ALLOWLIST = "1"
$env:AGENTSWARM_EXPECT_DISPATCH = "1"
$env:AGENTSWARM_EXPECT_REGISTRATION_AUTH = "1"

python scripts/verify_model_allowlist_staging.py $ApiUrl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:AGENTSWARM_VERIFY_QUICK = "1"
python scripts/verify_production_staging.py $ApiUrl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Staging model allowlist hardening verified: $ApiUrl"
