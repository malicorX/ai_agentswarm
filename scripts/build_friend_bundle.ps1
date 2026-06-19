# Build volunteer .exe and zip a folder you can send to a friend (worker machine).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

& "$PSScriptRoot\build_volunteer_exe.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$BundleDir = Join-Path $RepoRoot "dist\AgentSwarm-friend"
$OutZip = Join-Path $RepoRoot "dist\AgentSwarm-friend.zip"
if (Test-Path $BundleDir) { Remove-Item -Recurse -Force $BundleDir }
New-Item -ItemType Directory -Force -Path $BundleDir | Out-Null

Copy-Item (Join-Path $RepoRoot "dist\AgentSwarmVolunteer.exe") $BundleDir
Copy-Item (Join-Path $RepoRoot "client\FRIEND_README.txt") $BundleDir

if (Test-Path $OutZip) { Remove-Item -Force $OutZip }
Compress-Archive -Path (Join-Path $BundleDir "*") -DestinationPath $OutZip

Write-Host ""
Write-Host "Friend bundle:" -ForegroundColor Green
Write-Host "  Folder: $BundleDir"
Write-Host "  Zip:    $OutZip"
Write-Host ""
Write-Host "Send the zip. Your friend still needs Docker Desktop and network access to your platform URL."
