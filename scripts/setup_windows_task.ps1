[CmdletBinding()]
param(
    [string]$TaskName = "Marketplace Discord Bot",
    [string]$ProjectDirectory,
    [switch]$StartNow,
    [switch]$Remove
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module ScheduledTasks -ErrorAction Stop

if ($Remove) {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

    if ($null -eq $existingTask) {
        Write-Host "Scheduled task '$TaskName' is not registered."
        exit 0
    }

    if ($existingTask.State -eq "Running") {
        Stop-ScheduledTask -TaskName $TaskName
    }

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
    exit 0
}

if ([string]::IsNullOrWhiteSpace($ProjectDirectory)) {
    $ProjectDirectory = Split-Path -Parent $PSScriptRoot
}

$resolvedProjectDirectory = (Resolve-Path -LiteralPath $ProjectDirectory).Path
$pythonPath = Join-Path $resolvedProjectDirectory ".venv\Scripts\python.exe"
$mainPath = Join-Path $resolvedProjectDirectory "main.py"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Virtual-environment Python was not found at '$pythonPath'. Create .venv and install the project dependencies first."
}

if (-not (Test-Path -LiteralPath $mainPath -PathType Leaf)) {
    throw "Bot entry point was not found at '$mainPath'. Run this script from the repository's scripts directory or pass -ProjectDirectory."
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$quotedMainPath = '"{0}"' -f $mainPath

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument $quotedMainPath `
    -WorkingDirectory $resolvedProjectDirectory

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser

$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Starts the Marketplace Discord Bot when the current Windows user signs in." `
    -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' for $currentUser."
Write-Host "Project directory: $resolvedProjectDirectory"

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started scheduled task '$TaskName'."
}
else {
    Write-Host "The task will start at the next sign-in. Use -StartNow to start it immediately."
}
