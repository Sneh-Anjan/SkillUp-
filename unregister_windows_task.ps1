param([string]$District="Pune")
Unregister-ScheduledTask -TaskName "SkillUp-Daily-Market-Refresh-$District" -Confirm:$false
