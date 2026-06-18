# Trust theebie host keys on sparky workers so git ls-remote / clone works (D0 preflight).
param(
    [string]$TheebieHost = $(if ($env:AGENTSWARM_GIT_SSH_HOST) { $env:AGENTSWARM_GIT_SSH_HOST } else { "theebie.de" }),
    [string[]]$WorkerHosts = @(
        $(if ($env:AGENTSWARM_SPARKY1_HOST) { $env:AGENTSWARM_SPARKY1_HOST } else { "sparky1" }),
        $(if ($env:AGENTSWARM_SPARKY2_HOST) { $env:AGENTSWARM_SPARKY2_HOST } else { "sparky2" })
    ),
    [string]$GitRepoUrl = $env:AGENTSWARM_GIT_REPO_URL
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

foreach ($worker in $WorkerHosts | Select-Object -Unique) {
    Write-Host "Installing $TheebieHost host key on $worker ..."
    $cmd = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/known_hosts && ssh-keyscan -H $TheebieHost 2>/dev/null >> ~/.ssh/known_hosts"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        ssh $worker $cmd 2>&1 | Out-Null
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($GitRepoUrl) {
        $check = (ssh $worker "git ls-remote $GitRepoUrl HEAD 2>/dev/null && echo ok || echo fail") -join "`n"
        if ($check -notmatch "\bok\b") {
            Write-Error "git ls-remote still fails on $worker for $GitRepoUrl"
        }
        Write-Host "OK: $worker git ls-remote"
    } else {
        Write-Host "OK: $worker known_hosts updated (set AGENTSWARM_GIT_REPO_URL to verify clone)"
    }
}

Write-Host "Sparky git SSH trust configured."
