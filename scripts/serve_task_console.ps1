# AgentSwarm task console - operator UI.
# Default on Windows: native desktop window. Use -Browser for http://127.0.0.1:8765 only.
param(
    [switch]$Browser,
    [switch]$Native,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# Default: native desktop window (builds on first run if needed).
# Pass -Browser only when you explicitly want Chrome/Edge instead.
if (-not $Browser) {
    $NativeExe = @(
        (Join-Path $Root "dist\agentswarm-task-console.exe"),
        (Join-Path $Root "apps\agentswarm-task-console\target\release\agentswarm-task-console.exe")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $NativeExe) {
        Write-Host "Native app not built yet. Building now..." -ForegroundColor Yellow
        & "$PSScriptRoot\start_task_console_app.ps1" -Build
    } else {
        & "$PSScriptRoot\start_task_console_app.ps1"
    }
    exit $LASTEXITCODE
}

$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }
try {
    . "$PSScriptRoot\ensure_staging_env.ps1" -ApiUrl $ApiUrl
} catch {
    Write-Warning "Could not load staging secrets via SSH: $_"
    Write-Warning "Dispatch will fail unless AGENTSWARM_BOOTSTRAP_TOKEN is set (assignment secret is for volunteers only)."
}

$env:AGENTSWARM_REPO_ROOT = $Root
$Port = if ($env:AGENTSWARM_TASK_CONSOLE_PORT) { $env:AGENTSWARM_TASK_CONSOLE_PORT } else { "8765" }
$ConsoleUrl = "http://127.0.0.1:$Port"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "  Task console (browser mode)" -ForegroundColor Cyan
Write-Host "  URL: $ConsoleUrl" -ForegroundColor Green
Write-Host "  Tip: omit -Browser to use the native desktop window instead"
Write-Host "  Press Ctrl+C to stop the server."
Write-Host ""

if (-not $NoBrowser) {
    $openBrowser = {
        param($Url, $PortNum)
        $probe = "http://127.0.0.1:$PortNum/api/config"
        for ($i = 0; $i -lt 40; $i++) {
            try {
                $null = Invoke-WebRequest -Uri $probe -UseBasicParsing -TimeoutSec 1
                Start-Process $Url
                return
            } catch {
                Start-Sleep -Milliseconds 400
            }
        }
        Start-Process $Url
    }
    Start-Job -ScriptBlock $openBrowser -ArgumentList $ConsoleUrl, $Port | Out-Null
}

& $Python -m tools.task_console.server
