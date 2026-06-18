# Run an engineering goal with Windows VM sandbox testing (D4).
# Mock mode (no Hyper-V): set AGENTSWARM_WINDOWS_SANDBOX_MOCK=1
# Hyper-V pool: set AGENTSWARM_WINDOWS_VM_NAME and ensure guest has Python + pytest.
param(
    [string]$TaskFile = "tasks/example-primes-windows-sandbox.txt"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:AGENTSWARM_WINDOWS_SANDBOX = "1"
$env:AGENTSWARM_REPO_ROOT = $Root

if (-not $env:AGENTSWARM_WINDOWS_SANDBOX_MOCK) {
    $hyperv = (Get-Module -ListAvailable Hyper-V) -ne $null
    if (-not $hyperv) {
        Write-Host "Hyper-V module not found; enabling mock Windows sandbox (AGENTSWARM_WINDOWS_SANDBOX_MOCK=1)."
        $env:AGENTSWARM_WINDOWS_SANDBOX_MOCK = "1"
    }
}

$resolvedTaskFile = $TaskFile
if (-not [System.IO.Path]::IsPathRooted($TaskFile)) {
    $resolvedTaskFile = Join-Path $Root $TaskFile
}

Write-Host "Windows sandbox workers register sandbox.windows.build + sandbox.windows.test"
& "$PSScriptRoot\run_task_staging.ps1" -TaskFile $resolvedTaskFile
exit $LASTEXITCODE
