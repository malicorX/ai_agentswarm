# Phase 23 close-out: SDK config tests + weekly MCP smoke (P23.11).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pytest -q platform/tests agents/tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location packages/sdk-typescript
try {
    npm test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

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

$env:AGENTSWARM_EXPECT_DISPATCH = "1"
$env:AGENTSWARM_VERIFY_QUICK = "1"
Remove-Item Env:AGENTSWARM_VERIFY_FULL -ErrorAction SilentlyContinue
python scripts/verify_production_staging.py $ApiUrl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Phase 23 close-out checks OK. Tag with:"
Write-Host "  git tag v0.24.0-phase23 && git push origin v0.24.0-phase23"
