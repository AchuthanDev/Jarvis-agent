param(
    [switch]$AutoStart
)

$ErrorActionPreference = "Stop"
$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $AgentDir ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$Pip = Join-Path $VenvDir "Scripts\pip.exe"
$TaskName = "JarvisWindowsAgent"

Set-Location $AgentDir

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.11+ from python.org or the Microsoft Store."
}

if (-not (Test-Path $VenvDir)) {
    py -3 -m venv $VenvDir
}

& $Python -m pip install --upgrade pip
& $Pip install -r (Join-Path $AgentDir "requirements.txt")

if (-not (Test-Path (Join-Path $AgentDir ".env"))) {
    Copy-Item (Join-Path $AgentDir ".env.example") (Join-Path $AgentDir ".env")
    Write-Host "Created .env from .env.example. Edit it before registering."
}

if ($AutoStart) {
    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$AgentDir\start.ps1`""
    $Trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Description "JARVIS Windows companion agent" -Force | Out-Null
    Write-Host "Auto-start task registered: $TaskName"
}

Write-Host "Install complete."
Write-Host "Next: edit .env, then run .\start.ps1 after registration."
