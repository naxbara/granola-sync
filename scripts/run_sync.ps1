<#
.SYNOPSIS
    Non-interactive Granola -> Obsidian sync for scheduled/unattended runs.

.DESCRIPTION
    Computes a rolling window at run time and syncs it. A rolling window (rather
    than a strict 24h "daily") survives skipped runs: if a day is missed, the
    next run still catches the pending meetings. Dedup + note updates make
    re-scanning the window idempotent and nearly free.

    No `pause` — meant to be driven by Task Scheduler (see install_scheduled_task.ps1).

.PARAMETER Window
    Days back to sync. Default 3. Use 0 for the strict last-24h "daily" mode.
#>
[CmdletBinding()]
param(
    [int]$Window = 3,
    [string]$ConfigPath
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot

if (-not $ConfigPath) { $ConfigPath = Join-Path $RepoRoot "config.yaml" }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw "Could not find 'python' or 'py' on PATH." }

if ($Window -le 0) {
    & $python -m granola_sync --mode=daily --config $ConfigPath
} else {
    $from = (Get-Date).AddDays(-$Window).ToString('yyyy-MM-dd')
    & $python -m granola_sync --mode=historical --from=$from --config $ConfigPath
}

exit $LASTEXITCODE
