param(
    [switch]$RemoveConfig
)

$ErrorActionPreference = "Stop"
$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "JarvisWindowsAgent"

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Task) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task: $TaskName"
}

$VenvDir = Join-Path $AgentDir ".venv"
if (Test-Path $VenvDir) {
    Remove-Item $VenvDir -Recurse -Force
    Write-Host "Removed virtual environment."
}

if ($RemoveConfig) {
    $Config = Join-Path $AgentDir ".env"
    if (Test-Path $Config) {
        Remove-Item $Config -Force
        Write-Host "Removed .env."
    }
}

Write-Host "Uninstall complete."
