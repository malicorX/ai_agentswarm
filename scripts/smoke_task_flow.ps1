param(
    [string]$PlatformUrl = "http://127.0.0.1:8000",
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
pip install -q -e "./platform[dev]" pytest httpx

$env:AGENTSWARM_PLATFORM_URL = $PlatformUrl
$env:AGENTSWARM_DB = Join-Path $RepoRoot "platform\data\smoke.db"
if (Test-Path $env:AGENTSWARM_DB) { Remove-Item $env:AGENTSWARM_DB -Force }

$platformJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    $env:AGENTSWARM_DB = Join-Path $root "platform\data\smoke.db"
    & "$root\.venv\Scripts\python.exe" -m uvicorn agentswarm_platform.main:app --app-dir "$root\platform\src" --host 127.0.0.1 --port 8000
} -ArgumentList $RepoRoot

try {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $r = Invoke-RestMethod -Uri "$PlatformUrl/health" -TimeoutSec 2
            if ($r.status -eq "ok") { break }
        } catch {}
        if ((Get-Date) -gt $deadline) { throw "Platform failed to start" }
        Start-Sleep -Milliseconds 500
    } while ($true)

    python -c @"
import os
import httpx
from agentswarm_platform.crypto import generate_keypair, public_key_b64, sign_payload

url = os.environ['AGENTSWARM_PLATFORM_URL']
pub, priv = generate_keypair()
agent_id = httpx.post(f'{url}/agents/register', json={
    'public_key': public_key_b64(pub),
    'owner': 'smoke',
    'capabilities': ['codewriter'],
}).json()['agent_id']
task = httpx.post(f'{url}/tasks', json={
    'task_type': 'codewriter.patch',
    'capability_required': 'codewriter',
    'payload': {'file': 'index.html', 'insert': '<!-- smoke -->'},
}).json()
claim = httpx.post(f'{url}/tasks/{task["task_id"]}/claim', json={'agent_id': agent_id}).json()
result = {'applied': True}
sig = sign_payload(priv, {'task_id': task['task_id'], 'result': result})
httpx.post(f'{url}/tasks/submit', json={
    'claim_token': claim['claim_token'],
    'result': result,
    'signature': sig,
}).raise_for_status()
print('smoke: create -> claim -> submit OK')
"@

    Write-Host "smoke_task_flow.ps1 complete"
}
finally {
    Stop-Job $platformJob -ErrorAction SilentlyContinue
    Remove-Job $platformJob -Force -ErrorAction SilentlyContinue
}
