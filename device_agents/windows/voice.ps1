$ErrorActionPreference = "Stop"
$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $AgentDir "..\..")
$Python = Join-Path $AgentDir ".venv\Scripts\python.exe"
$VoiceArgs = @($args)

if (-not (Test-Path $Python)) {
    throw "Virtual environment not found. Run .\install.ps1 and .\install-voice.ps1 first."
}

if (-not $VoiceArgs -or $VoiceArgs.Count -eq 0) {
    throw "Choose --list-devices, --test-mic, --test-tts, --push-to-talk, or --wake-word."
}

$ArgsList = @("--config", (Join-Path $AgentDir ".env")) + $VoiceArgs

Set-Location $AgentDir
$env:PYTHONPATH = "$RepoRoot"
& $Python -m device_agents.windows.voice.cli @ArgsList
