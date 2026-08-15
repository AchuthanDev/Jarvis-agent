$ErrorActionPreference = "Stop"
$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $AgentDir ".venv\Scripts\python.exe"
$Pip = Join-Path $AgentDir ".venv\Scripts\pip.exe"

if (-not (Test-Path $Python)) {
    & (Join-Path $AgentDir "install.ps1")
}

Set-Location $AgentDir
& $Python -m pip install --upgrade pip
& $Pip install -r (Join-Path $AgentDir "requirements-voice.txt")

Write-Host "Voice dependencies installed."
Write-Host "Next: run .\voice.ps1 --list-devices"
