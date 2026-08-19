<#
Registers the "GmailIngest" Windows Task Scheduler job.
Run this manually, once, from an elevated or normal PowerShell prompt
(elevation not required for a per-user task):

    .\register_task.ps1

Prerequisites before running this:
  1. python -m venv .venv ; .venv\Scripts\pip install -e .
  2. credentials.json placed in this folder (from Google Cloud Console)
  3. Run once manually so the OAuth browser consent happens interactively:
        .venv\Scripts\python -m gmail_ingest.cli update
     and confirm token.json was created.

This script itself only registers the schedule - it does not run the sync.
#>

$ProjectDir = $PSScriptRoot
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m gmail_ingest.cli update" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::MaxValue)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName "GmailIngest" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Polls Gmail for new messages every 30 minutes and indexes them locally."

Write-Host "Registered task 'GmailIngest'. View/edit it in Task Scheduler, or run:"
Write-Host "  Start-ScheduledTask -TaskName GmailIngest   # to trigger a run now"
Write-Host "  Unregister-ScheduledTask -TaskName GmailIngest -Confirm:`$false   # to remove it"
