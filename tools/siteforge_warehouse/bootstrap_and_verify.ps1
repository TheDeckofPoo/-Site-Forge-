# One-shot: reset siteforge_app password, ensure DB, write URL file, verify LOGIN_OK
# ASCII-only for Windows PowerShell 5.1 safety.
$ErrorActionPreference = "Stop"
$Psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Out = Join-Path $Repo "config\local_database_url.txt"

Write-Host "=== Site Forge DB reset + verify ===" -ForegroundColor Cyan
Write-Host "Repo: $Repo"

if (-not (Test-Path $Psql)) {
  throw "psql not found at $Psql"
}

$adminPass = Read-Host -AsSecureString "postgres SUPERUSER password"
$appPass = Read-Host -AsSecureString "NEW siteforge_app password (will reset role)"
$appPass2 = Read-Host -AsSecureString "Confirm NEW siteforge_app password"

$b1 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($appPass)
$b2 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($appPass2)
$pw = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b1)
$pw2 = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b2)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b1)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b2)
if ($pw -ne $pw2) { throw "passwords do not match" }

$ba = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($adminPass)
$admin = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ba)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ba)

$env:PGPASSWORD = $admin
$sqlPw = $pw.Replace("'", "''")

function Get-PsqlScalar([string]$User, [string]$Db, [string]$Sql) {
  $raw = & $Psql -U $User -h localhost -d $Db -tAc $Sql 2>$null
  if ($null -eq $raw) { return "" }
  return (($raw | Out-String).Trim())
}

Write-Host "Checking postgres admin login..." -ForegroundColor Yellow
$adminWho = Get-PsqlScalar "postgres" "postgres" "SELECT current_user"
if ($LASTEXITCODE -ne 0 -or $adminWho -ne "postgres") {
  throw "postgres admin login failed"
}
Write-Host "POSTGRES_ADMIN_LOGIN_OK"

Write-Host "Resetting role siteforge_app..." -ForegroundColor Yellow
& $Psql -U postgres -h localhost -d postgres -v ON_ERROR_STOP=1 -c @"
DO `$`$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'siteforge_app') THEN
    CREATE ROLE siteforge_app LOGIN PASSWORD '$sqlPw';
  ELSE
    ALTER ROLE siteforge_app WITH LOGIN PASSWORD '$sqlPw';
  END IF;
END `$`$;
"@
if ($LASTEXITCODE -ne 0) { throw "role reset failed - check postgres superuser password" }
Write-Host "ROLE_RESET_OK"

$exists = Get-PsqlScalar "postgres" "postgres" "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_database WHERE datname='siteforge') THEN 1 ELSE 0 END;"
if ($exists -eq "0" -or [string]::IsNullOrWhiteSpace($exists)) {
  & $Psql -U postgres -h localhost -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE siteforge OWNER siteforge_app;"
  if ($LASTEXITCODE -ne 0) { throw "database create failed" }
} else {
  & $Psql -U postgres -h localhost -d postgres -v ON_ERROR_STOP=1 -c "ALTER DATABASE siteforge OWNER TO siteforge_app;"
  if ($LASTEXITCODE -ne 0) { throw "database owner alter failed" }
}
& $Psql -U postgres -h localhost -d siteforge -v ON_ERROR_STOP=1 -c "GRANT ALL ON SCHEMA public TO siteforge_app; ALTER SCHEMA public OWNER TO siteforge_app;"
if ($LASTEXITCODE -ne 0) { throw "schema grant failed" }
Write-Host "DATABASE_OK"

$env:PGPASSWORD = $pw
$who = Get-PsqlScalar "siteforge_app" "siteforge" "SELECT current_user || ' @ ' || current_database()"
if ($LASTEXITCODE -ne 0 -or $who -notlike "siteforge_app*") {
  throw "psql login as siteforge_app failed"
}
Write-Host "SITEFORGE_APP_PSQL_LOGIN_OK $who"

$escaped = [System.Uri]::EscapeDataString($pw)
$url = "postgresql+psycopg://siteforge_app:${escaped}@localhost:5432/siteforge"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($Out, ($url + "`n"), $utf8NoBom)
Write-Host "Wrote $Out"

$env:PGPASSWORD = $null
$admin = $null
$pw = $null
$pw2 = $null
$sqlPw = $null
$escaped = $null
$url = $null
[GC]::Collect()

Set-Location $Repo
$py = @"
from tools.siteforge_warehouse.config import get_database_url
from sqlalchemy import create_engine, text
u = get_database_url()
if not u:
    raise SystemExit('URL file missing')
e = create_engine(u)
c = e.connect()
print('SITEFORGE_APP_PYTHON_LOGIN_OK', c.execute(text('select current_user')).scalar())
c.close()
print('LOGIN_OK')
"@
python -c $py
if ($LASTEXITCODE -ne 0) { throw "Python LOGIN_OK failed" }

Write-Host "All checkpoints passed. Tell Anton to continue with Alembic." -ForegroundColor Green
