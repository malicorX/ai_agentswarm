# Distributed D6 demo: sparky2=codewriter (git push), sparky1=sandbox tester (git-in-container), local=reviewer.
param(
    [switch]$SyncRemotes,
    [switch]$InitGitWorkspace
)

& "$PSScriptRoot\demo_distributed_engineering_git.ps1" -GitInContainer -SyncRemotes:$SyncRemotes -InitGitWorkspace:$InitGitWorkspace @args
exit $LASTEXITCODE
