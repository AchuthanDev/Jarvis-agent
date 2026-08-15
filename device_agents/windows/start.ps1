$ErrorActionPreference = "Stop"
$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $AgentDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Virtual environment not found. Run .\install.ps1 first."
}

Set-Location $AgentDir
& $Python agent.py --config (Join-Path $AgentDir ".env") run
