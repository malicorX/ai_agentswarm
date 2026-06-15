# Creative subjective path demo (dispatch mode) — legacy parallel clients
# Prefer: scripts/demo_volunteer_subjective.py (sequential volunteer clients, P8.3)
# Requires platform running with:
#   $env:AGENTSWARM_ASSIGNMENT_MODE = "dispatch"
#   $env:AGENTSWARM_ASSIGNMENT_SECRET = "dev-secret"

$ErrorActionPreference = "Stop"
$BaseUrl = if ($env:AGENTSWARM_PLATFORM_URL) { $env:AGENTSWARM_PLATFORM_URL } else { "http://127.0.0.1:8000" }

Write-Host "Creative subjective demo against $BaseUrl"

python scripts/run_dispatch_client.py --capabilities coordinator --owner demo-coord --loops 1 --wait-sec 5 &
python scripts/run_dispatch_client.py --capabilities creative --owner demo-creative --loops 1 --wait-sec 5 &
python scripts/run_dispatch_client.py --capabilities reviewer --owner demo-reviewer-1 --loops 1 --wait-sec 5 &
python scripts/run_dispatch_client.py --capabilities reviewer --owner demo-reviewer-2 --loops 1 --wait-sec 5 &
python scripts/run_dispatch_client.py --capabilities reviewer --owner demo-reviewer-3 --loops 1 --wait-sec 5 &

Start-Sleep -Seconds 2

# Poster registers and posts goal via inline Python
python -c @"
import httpx, json
from agentswarm_platform.crypto import generate_keypair, public_key_b64

base = '$BaseUrl'
pub, priv = generate_keypair()
r = httpx.post(f'{base}/agents/register', json={
    'public_key': public_key_b64(pub),
    'owner': 'demo-poster',
    'capabilities': ['codewriter'],
})
r.raise_for_status()
poster_id = r.json()['agent_id']
goal = httpx.post(f'{base}/creative/goals', json={
    'poster_agent_id': poster_id,
    'brief': 'Write a haiku about volunteer AI compute',
    'rubric': [{'id': 'quality', 'weight': 1.0}],
    'min_reviewers': 3,
})
goal.raise_for_status()
print('goal_id', goal.json()['goal_id'])
"@

Write-Host "Waiting for dispatch clients..."
Wait-Process -Name python -ErrorAction SilentlyContinue
Write-Host "Done. Check GET /creative/goals/{goal_id} on the platform."
