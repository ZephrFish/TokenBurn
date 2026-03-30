# Collect local LLM session data and push to the central repo.
# Run this on Windows machines.
#
# Usage:
#   .\sync.ps1                   # auto-detect hostname
#   .\sync.ps1 -Name mybox       # custom machine name

param([string]$Name = "")

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Pull latest
git pull --rebase --quiet 2>$null

# Collect local data
$collectArgs = @()
if ($Name) { $collectArgs += "--name", $Name }
python collect.py @collectArgs

# Stage and push
$machine = if ($Name) { $Name } else { $env:COMPUTERNAME.ToLower() }

git add "machines/data-*.json"
$diff = git diff --cached --quiet 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "No changes to push."
} else {
    git commit -m "update data from $machine"
    git push
    Write-Host "Pushed data from $machine."
}
