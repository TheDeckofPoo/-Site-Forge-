# Writes gitignored config/local_database_url.txt interactively.
# ASCII-only for Windows PowerShell 5.1 safety.
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Out = Join-Path $Repo "config\local_database_url.txt"

Write-Host "Writing: $Out" -ForegroundColor Cyan
$user = Read-Host "DB user [siteforge_app]"
if ([string]::IsNullOrWhiteSpace($user)) { $user = "siteforge_app" }
$hostPort = Read-Host "Host:port [localhost:5432]"
if ([string]::IsNullOrWhiteSpace($hostPort)) { $hostPort = "localhost:5432" }
$db = Read-Host "Database [siteforge]"
if ([string]::IsNullOrWhiteSpace($db)) { $db = "siteforge" }
$sec = Read-Host -AsSecureString "Password for $user"
$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$pw = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)

$escaped = [System.Uri]::EscapeDataString($pw)
$url = "postgresql+psycopg://${user}:${escaped}@${hostPort}/${db}"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($Out, ($url + "`n"), $utf8NoBom)
$pw = $null
$escaped = $null
$url = $null
[GC]::Collect()
Write-Host "Wrote local_database_url.txt (gitignored, UTF-8 no BOM)." -ForegroundColor Green
Write-Host "File exists: $(Test-Path $Out)"
