param(
  [string]$Python = "$PSScriptRoot\..\backend\.venv\Scripts\python.exe",
  [string]$Project = "$PSScriptRoot\..",
  [string]$District = "Pune",
  [string]$Time = "09:00"
)
$script = Join-Path $Project "scripts\run_sync.py"
$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$script`"" -WorkingDirectory $Project
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
Register-ScheduledTask -TaskName "SkillUp-Daily-Market-Refresh-$District" -Action $action -Trigger $trigger -Description "Daily incremental SkillUp market refresh for $District" -Force
Write-Host "Registered daily SkillUp refresh for $District at $Time"
