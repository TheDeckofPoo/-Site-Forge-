# Site Forge local PostgreSQL bootstrap (interactive passwords - never logged to Git)
# ASCII-only for Windows PowerShell 5.1 safety.
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File tools\siteforge_warehouse\bootstrap_local_pg.ps1

$ErrorActionPreference = "Stop"
$Psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

if (-not (Test-Path $Psql)) {
  Write-Error "psql not found at $Psql - adjust path if your install differs."
}

Write-Host "=== Site Forge PostgreSQL bootstrap ===" -ForegroundColor Cyan
Write-Host "Passwords are prompted interactively and are NOT written to disk by this script."
Write-Host ""

$adminPass = Read-Host -AsSecureString "Enter postgres SUPERUSER password"
$appPass = Read-Host -AsSecureString "Choose siteforge_app password"
$appPassConfirm = Read-Host -AsSecureString "Confirm siteforge_app password"

$bstr1 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($appPass)
$bstr2 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($appPassConfirm)
$plainApp = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr1)
$plainApp2 = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr2)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr1)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr2)
if ($plainApp -ne $plainApp2) {
  Write-Error "siteforge_app passwords do not match."
}

$bstrA = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($adminPass)
$plainAdmin = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstrA)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrA)

$env:PGPASSWORD = $plainAdmin
$sqlPass = $plainApp.Replace("'", "''")

$sql = @"
SELECT 'bootstrap_start';
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'siteforge_app') THEN
    CREATE ROLE siteforge_app LOGIN PASSWORD '$sqlPass';
  ELSE
    ALTER ROLE siteforge_app WITH LOGIN PASSWORD '$sqlPass';
  END IF;
END
`$`$;
SELECT 'role_ready';
"@

& $Psql -U postgres -h localhost -d postgres -v ON_ERROR_STOP=1 -c $sql
if ($LASTEXITCODE -ne 0) { throw "role create failed" }

$exists = & $Psql -U postgres -h localhost -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='siteforge'"
if ($exists.Trim() -ne "1") {
  & $Psql -U postgres -h localhost -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE siteforge OWNER siteforge_app;"
  if ($LASTEXITCODE -ne 0) { throw "database create failed" }
} else {
  & $Psql -U postgres -h localhost -d postgres -v ON_ERROR_STOP=1 -c "ALTER DATABASE siteforge OWNER TO siteforge_app;"
}

& $Psql -U postgres -h localhost -d siteforge -v ON_ERROR_STOP=1 -c "GRANT ALL ON SCHEMA public TO siteforge_app;"

$env:PGPASSWORD = $null
$plainAdmin = $null
$plainApp = $null
$plainApp2 = $null
$sqlPass = $null
[GC]::Collect()

Write-Host ""
Write-Host "Database siteforge and role siteforge_app are ready." -ForegroundColor Green
Write-Host "Next: run bootstrap_and_verify.ps1 OR write_local_db_url.ps1, then Alembic." -ForegroundColor Yellow
