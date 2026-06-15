# Phase 19 close-out: SDK dispatch helpers (P19.11).
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

Write-Host "Phase 19 close-out checks OK. Tag with:"
Write-Host "  git tag v0.20.0-phase19 && git push origin v0.20.0-phase19"
