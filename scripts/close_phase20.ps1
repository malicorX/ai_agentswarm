# Phase 20 close-out: SDK dispatch e2e + staging verify (P20.11).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pytest -q platform/tests agents/tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m pytest -q platform/tests/test_sdk_dispatch.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -c @"
from pathlib import Path
import subprocess
import sys

bad = [str(p) for p in Path('scripts').rglob('*.sh') if b'\r' in p.read_bytes()]
if bad:
    print('CRLF found in shell scripts:', ', '.join(bad), file=sys.stderr)
    raise SystemExit(1)

for path in sorted(Path('scripts').rglob('*.sh')):
    subprocess.run(['bash', '-n', path.as_posix()], check=True)
print('Shell script hygiene OK')
"@
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location packages/sdk-typescript
npm run test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Pop-Location

$HostSsh = if ($env:AGENTSWARM_THEEBIE_HOST) { $env:AGENTSWARM_THEEBIE_HOST } else { "root@theebie.de" }
$EnvFile = if ($env:AGENTSWARM_PLATFORM_ENV_FILE) { $env:AGENTSWARM_PLATFORM_ENV_FILE } else { "/etc/agentswarm/platform.env" }
$ApiUrl = if ($env:AGENTSWARM_STAGING_API_URL) { $env:AGENTSWARM_STAGING_API_URL } else { "https://theebie.de/agentswarm/api" }

if (-not $env:AGENTSWARM_BOOTSTRAP_TOKEN) {
    $boot = ssh $HostSsh "grep -E '^AGENTSWARM_BOOTSTRAP_TOKEN=' $EnvFile | cut -d= -f2-"
    if (-not $boot) {
        Write-Error "Could not read AGENTSWARM_BOOTSTRAP_TOKEN from ${HostSsh}:${EnvFile}"
    }
    $env:AGENTSWARM_BOOTSTRAP_TOKEN = $boot.Trim()
}

python scripts/verify_sdk_dispatch_staging.py $ApiUrl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Phase 20 close-out checks OK. Tag with:"
Write-Host "  git tag v0.21.0-phase20 && git push origin v0.21.0-phase20"
