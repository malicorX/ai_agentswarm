# Enable reviewer VRAM hardware gates on theebie.de (P9.1).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$HostSsh = if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }
$RemoteRoot = if ($env:AGENTSWARM_THEEBIE_ROOT) { $env:AGENTSWARM_THEEBIE_ROOT } else { "/opt/agentswarm" }

scp scripts/remote/harden_platform_hardware_gates_theebie.sh "${HostSsh}:${RemoteRoot}/scripts/remote/"
ssh $HostSsh "bash ${RemoteRoot}/scripts/remote/harden_platform_hardware_gates_theebie.sh"

$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
$env:AGENTSWARM_EXPECT_HARDWARE_GATES = "1"
python scripts/verify_hardware_gates_staging.py $ApiUrl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
