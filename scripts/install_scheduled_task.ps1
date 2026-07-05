<#
.SYNOPSIS
    Register a daily, non-interactive Granola -> Obsidian sync as a Windows
    Scheduled Task.

.DESCRIPTION
    Runs scripts\run_sync.ps1 every day at the given time with the repo as the
    working directory, so config.yaml and logs/ resolve there. run_sync uses a
    rolling window (default 3 days) so a skipped run is caught up on the next
    one. Unlike the double-click .bat launchers, this task has no `pause` and
    runs unattended.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -Time 09:00

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -Time 08:30 -Window 7

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$Time = "09:00",
    [int]$Window = 3,
    [string]$TaskName = "GranolaSyncDaily",
    [string]$ConfigPath,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent

if ($Uninstall) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "Removed scheduled task '$TaskName'."
    } catch {
        Write-Warning "No scheduled task named '$TaskName' was found."
    }
    return
}

if (-not $ConfigPath) { $ConfigPath = Join-Path $RepoRoot "config.yaml" }
if (-not (Test-Path $ConfigPath)) {
    Write-Warning "Config not found at $ConfigPath. Copy config.example.yaml to config.yaml and edit it before the first run."
}

# Sanity-check that a Python launcher exists (run_sync.ps1 resolves it again).
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw "Could not find 'python' or 'py' on PATH. Install Python 3.11+ and 'pip install -e .' in this repo first." }

# The task runs the non-interactive rolling-window sync (no pause).
$runScript = Join-Path $PSScriptRoot "run_sync.ps1"
$psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`" -Window $Window -ConfigPath `"$ConfigPath`""

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered daily task '$TaskName' at $Time (rolling $Window-day window)."
Write-Host "  Runs: powershell -File $runScript -Window $Window"
Write-Host "  Working dir: $RepoRoot"
Write-Host ""
Write-Host "Verify:   schtasks /query /tn $TaskName"
Write-Host "Run now:  schtasks /run /tn $TaskName"
Write-Host "Remove:   powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -Uninstall"
