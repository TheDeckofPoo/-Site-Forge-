# Quick launcher — backs up entire C:\dev\worktree to D:\WorktTree
# Usage:
#   .\Run-Backup-Now.ps1           # incremental (default)
#   .\Run-Backup-Now.ps1 -Full     # copy everything again
param([switch]$Full)

$script = Join-Path $PSScriptRoot "Rockwell_GitHub\tools\backup\Backup-AllWorktreesToD.ps1"
if (-not (Test-Path $script)) {
    Write-Error "Backup script missing: $script"
    exit 1
}
& $script -Full:$Full
