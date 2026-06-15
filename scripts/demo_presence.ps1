$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$env:AGENTSWARM_ASSIGNMENT_MODE = "dispatch"
$env:AGENTSWARM_ASSIGNMENT_SECRET = "demo-dispatch-secret"
$env:AGENTSWARM_AUTH_DISABLED = "1"
$db = if ($env:AGENTSWARM_DB) { $env:AGENTSWARM_DB } else { Join-Path $PWD "platform\data\demo-presence.db" }
$env:AGENTSWARM_DB = $db
Remove-Item -Force $db -ErrorAction SilentlyContinue

pip install -q -e "./platform[dev]" httpx 2>$null
$uv = Start-Process -FilePath python -ArgumentList @(
    "-m", "uvicorn", "agentswarm_platform.main:app",
    "--app-dir", "platform/src", "--host", "127.0.0.1", "--port", "8010"
) -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2
try {
    python -c @"
import httpx
from agentswarm_platform.crypto import generate_keypair, public_key_b64

base = 'http://127.0.0.1:8010'

def register(owner, caps):
    pub, _ = generate_keypair()
    r = httpx.post(f'{base}/agents/register', json={
        'public_key': public_key_b64(pub), 'owner': owner, 'capabilities': caps,
    }, timeout=30)
    r.raise_for_status()
    return r.json()['agent_id']

poster = register('demo-poster', ['codewriter'])
reviewer = register('demo-reviewer', ['reviewer'])
for agent_id, caps in ((poster, ['codewriter']), (reviewer, ['reviewer'])):
    httpx.post(f'{base}/agents/{agent_id}/presence',
               json={'status': 'idle', 'capabilities': caps, 'ttl_sec': 120}, timeout=30).raise_for_status()
need = httpx.post(f'{base}/pool/need', json={
    'role': 'reviewer', 'capability_required': 'reviewer', 'task_type': 'reviewer.subjective',
    'payload': {'capsule': {'brief': 'demo review'}},
    'constraints': {'exclude_owners': ['demo-poster']},
}, timeout=30)
need.raise_for_status()
body = need.json()
assert body['assigned'], body
pending = httpx.get(f'{base}/agents/{reviewer}/assignments/pending', timeout=30)
pending.raise_for_status()
assert pending.json()['task_id'] == body['task_id']
print('demo_presence: pool assigned reviewer to idle client')
"@
} finally {
    Stop-Process -Id $uv.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "demo_presence.ps1 complete"
