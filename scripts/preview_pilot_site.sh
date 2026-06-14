#!/usr/bin/env bash
# Preview the combined pilot static site locally (same layout as GitHub Pages).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging/news-hub" "$staging/dashboard"
cp "$root/pilot/index.html" "$staging/"
cp -r "$root/pilot/news-hub/." "$staging/news-hub/"
cp -r "$root/pilot/dashboard/." "$staging/dashboard/"
port=8080
echo "Pilot preview: http://127.0.0.1:${port}/"
echo "Press Ctrl+C to stop."
cd "$staging"
exec python3 -m http.server "$port"
