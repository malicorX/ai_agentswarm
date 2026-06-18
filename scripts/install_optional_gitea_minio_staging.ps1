# Optional Gitea + MinIO on theebie (D3 demo forge/blob store).
# Not required when using bare git on theebie + platform artifact API.
param(
    [string]$HostSsh = $(if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }),
    [string]$RemoteRoot = $(if ($env:AGENTSWARM_PLATFORM_REMOTE_DIR) { $env:AGENTSWARM_PLATFORM_REMOTE_DIR } else { "/opt/agentswarm" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$remoteScript = Join-Path $Root "scripts\remote\install_optional_gitea_minio_theebie.sh"
if (-not (Test-Path $remoteScript)) {
    Write-Error "Missing $remoteScript"
}

Write-Host "Installing optional Gitea + MinIO on $HostSsh ..."
scp $remoteScript "${HostSsh}:${RemoteRoot}/scripts/remote/install_optional_gitea_minio_theebie.sh"
scp (Join-Path $Root "docs\infra\theebie\docker-compose.optional-gitea-minio.yml") "${HostSsh}:${RemoteRoot}/docs/infra/theebie/docker-compose.optional-gitea-minio.yml"
ssh $HostSsh "chmod +x '${RemoteRoot}/scripts/remote/install_optional_gitea_minio_theebie.sh' && bash '${RemoteRoot}/scripts/remote/install_optional_gitea_minio_theebie.sh'"
Write-Host "Optional Gitea + MinIO install finished. See docs/infra/theebie/optional-gitea-minio.md"
