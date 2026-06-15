# Restart staging platform and wait for health before subjective verify (P10.1).
$ErrorActionPreference = "Stop"
$HostSsh = if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }
$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }

ssh $HostSsh "systemctl restart agentswarm-platform"

for ($attempt = 1; $attempt -le 15; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "$ApiUrl/health" -Method Get
        if ($health.status -eq "ok") {
            Write-Host "Staging platform ready: $ApiUrl"
            exit 0
        }
    } catch {
        # retry
    }
    Start-Sleep -Seconds 2
}

Write-Error "Staging platform did not become healthy at $ApiUrl"
