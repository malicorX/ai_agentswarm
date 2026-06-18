# Enable per-goal forge deploy key minting on theebie (D1).
param(
    [string]$HostSsh = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$EnvFile = $(if ($env:AGENTSWARM_PLATFORM_ENV_FILE) { $env:AGENTSWARM_PLATFORM_ENV_FILE } else { "/etc/agentswarm/platform.env" }),
    [string]$ServiceName = "agentswarm-platform",
    [switch]$SkipAutoInstall
)

$ErrorActionPreference = "Stop"

function Set-EnvKv {
    param([string]$Key, [string]$Value)
    $hasKey = ssh $HostSsh "grep -q '^${Key}=' '$EnvFile' 2>/dev/null && echo yes || echo no"
    if ($hasKey.Trim() -eq "yes") {
        ssh $HostSsh "sed -i 's/^${Key}=.*/${Key}=${Value}/' '$EnvFile'"
    } else {
        ssh $HostSsh "echo '${Key}=${Value}' >> '$EnvFile'"
    }
}

Write-Host "Enabling AGENTSWARM_FORGE_MINT_KEYS on $HostSsh ..."
Set-EnvKv -Key "AGENTSWARM_FORGE_MINT_KEYS" -Value "1"
if (-not $SkipAutoInstall) {
    Write-Host "Enabling AGENTSWARM_FORGE_AUTO_INSTALL_KEYS (install deploy keys on goal create) ..."
    Set-EnvKv -Key "AGENTSWARM_FORGE_AUTO_INSTALL_KEYS" -Value "1"
}
ssh $HostSsh "systemctl restart '$ServiceName' && sleep 2 && curl -sf http://127.0.0.1:8010/health"
ssh $HostSsh "grep '^AGENTSWARM_FORGE_' '$EnvFile'"
Write-Host "Forge mint enabled and platform restarted."
