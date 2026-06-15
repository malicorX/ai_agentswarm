#!/usr/bin/env bash
# Phase 19 close-out: SDK dispatch helpers (P19.11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python -m pytest -q platform/tests agents/tests
python -m pytest -q platform/tests/test_sdk_dispatch.py

bad=()
while IFS= read -r -d '' path; do
  if grep -q $'\r' "$path"; then
    bad+=("$path")
  fi
done < <(find scripts -name '*.sh' -print0)
if ((${#bad[@]})); then
  echo "CRLF found in shell scripts: ${bad[*]}" >&2
  exit 1
fi
while IFS= read -r -d '' path; do
  bash -n "$path"
done < <(find scripts -name '*.sh' -print0)
echo "Shell script hygiene OK"

(
  cd packages/sdk-typescript
  npm run test
)

echo "Phase 19 close-out checks OK. Tag with:"
echo "  git tag v0.20.0-phase19 && git push origin v0.20.0-phase19"
