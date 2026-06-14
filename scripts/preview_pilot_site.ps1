#Requires -Version 5.1
<#
.SYNOPSIS
  Preview the combined pilot static site locally (same layout as GitHub Pages).
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$staging = Join-Path $env:TEMP "agentswarm-pilot-preview"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path (Join-Path $staging "news-hub") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $staging "dashboard") | Out-Null
Copy-Item (Join-Path $root "pilot\index.html") $staging
Copy-Item (Join-Path $root "pilot\news-hub\*") (Join-Path $staging "news-hub") -Recurse
Copy-Item (Join-Path $root "pilot\dashboard\*") (Join-Path $staging "dashboard") -Recurse
$port = 8080
Write-Host "Pilot preview: http://127.0.0.1:$port/"
Write-Host "Press Ctrl+C to stop."
Set-Location $staging
python -m http.server $port
