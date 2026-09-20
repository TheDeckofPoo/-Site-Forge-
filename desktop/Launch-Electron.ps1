# Site Forge — Electron launcher (separate from Rockwell Git)
$ErrorActionPreference = "Stop"

$desktopDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $desktopDir
Set-Location $desktopDir

function Find-Python {
    foreach ($cmd in @('py', 'python', 'python3')) {
        try {
            $v = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -or ($v -match 'Python')) { return $cmd }
        } catch {}
    }
    return $null
}

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  SITE FORGE' -ForegroundColor Cyan
Write-Host '  Docs · RUN · PLC Autogen · Ignition' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host 'ERROR: npm not found. Install Node.js from https://nodejs.org/' -ForegroundColor Red
    pause
    exit 1
}

$pythonExe = Find-Python
if (-not $pythonExe) {
    Write-Host 'WARN: Python not found — doc indexing and automation will not work.' -ForegroundColor Yellow
} else {
    Write-Host "OK: Python ($pythonExe)" -ForegroundColor Green
    $indexScript = Join-Path $repoRoot 'tools\scripts\index_docs.py'
    if (-not (Test-Path (Join-Path $repoRoot 'docs-index\documents.json'))) {
        Write-Host 'INDEX: Building training doc index (first run)...' -ForegroundColor Yellow
        & $pythonExe $indexScript
    }
}

function Repair-ElectronBinary {
    $destElectron = Join-Path $desktopDir 'node_modules\electron'
    $destDist = Join-Path $destElectron 'dist'
    $pathFile = Join-Path $destElectron 'path.txt'

    if (-not (Test-Path $destElectron)) {
        Write-Host 'INSTALL: Electron package...' -ForegroundColor Yellow
        npm install 2>&1 | Out-Null
    }

    # Try downloading the binary (uses Electron cache if already present)
    Write-Host 'REPAIR: Downloading Electron binary...' -ForegroundColor Yellow
    Remove-Item $destDist -Recurse -Force -ErrorAction SilentlyContinue
    $null = node -e @"
const { downloadArtifact } = require('@electron/get');
const extract = require('extract-zip');
const fs = require('fs');
const path = require('path');
const v = require('./node_modules/electron/package').version;
const dist = path.resolve('node_modules/electron/dist');
fs.mkdirSync(dist, { recursive: true });
downloadArtifact({ version: v, artifactName: 'electron', platform: 'win32', arch: 'x64' })
  .then((zip) => extract(zip, { dir: dist }))
  .then(() => fs.writeFileSync(path.resolve('node_modules/electron/path.txt'), 'electron.exe'))
  .catch((e) => { console.error(e.message); process.exit(1); });
"@ 2>&1
    if ((Test-Path $pathFile) -and (Test-Path (Join-Path $destDist 'electron.exe'))) {
        return $true
    }

    # Fallback: reuse Rockwell Git Electron (same version family)
    $rockwellDist = Join-Path (Split-Path -Parent $repoRoot) 'Rockwell_GitHub\desktop\node_modules\electron\dist'
    if (Test-Path (Join-Path $rockwellDist 'electron.exe')) {
        Write-Host 'REPAIR: Linking Electron from Rockwell Git install...' -ForegroundColor Yellow
        Remove-Item $destDist -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Junction -Path $destDist -Target $rockwellDist | Out-Null
        Set-Content -Path $pathFile -Value 'electron.exe' -NoNewline
        return (Test-Path (Join-Path $destDist 'electron.exe'))
    }
    return $false
}

function Test-ElectronBinary {
    $electronExe = Join-Path $desktopDir 'node_modules\electron\dist\electron.exe'
    $pathFile = Join-Path $desktopDir 'node_modules\electron\path.txt'
    return ((Test-Path $pathFile) -and (Test-Path $electronExe))
}

if (-not (Test-Path 'node_modules')) {
    Write-Host 'INSTALL: Electron (first time)...' -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'ERROR: npm install failed.' -ForegroundColor Red
        pause
        exit 1
    }
}

if (-not (Test-ElectronBinary)) {
    if (-not (Repair-ElectronBinary)) {
        Write-Host 'ERROR: Electron failed to install. Check network, then run:' -ForegroundColor Red
        Write-Host '  cd C:\Users\curtiskricke\worktrees\FortnaPlus\desktop' -ForegroundColor Red
        Write-Host '  npm install' -ForegroundColor Red
        pause
        exit 1
    }
    Write-Host 'OK: Electron repaired.' -ForegroundColor Green
}

# Runtime provenance snapshot — deterministic even if git is unavailable later
function Write-RuntimeBuildJson {
    $outPath = Join-Path $desktopDir '.runtime_build.json'
    $sha = $null
    $short = $null
    $branch = $null
    $gitRoot = $null
    try {
        Push-Location $repoRoot
        $sha = (git rev-parse HEAD 2>$null)
        $short = (git rev-parse --short HEAD 2>$null)
        $branch = (git rev-parse --abbrev-ref HEAD 2>$null)
        $gitRoot = (git rev-parse --show-toplevel 2>$null)
    } catch {
        # keep nulls; merge with existing file below
    } finally {
        Pop-Location
    }
    $started = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    $existingSha = $null
    $existingShort = $null
    $existingBranch = $null
    $existingRoot = $null
    if (Test-Path $outPath) {
        try {
            $existing = Get-Content -Raw -Path $outPath | ConvertFrom-Json
            $existingSha = $existing.gitSha
            $existingShort = $existing.gitShaShort
            $existingBranch = $existing.branch
            $existingRoot = $existing.repoRoot
        } catch {}
    }
    if (-not $sha) { $sha = $existingSha }
    if (-not $short) { $short = $existingShort }
    if (-not $branch) { $branch = $existingBranch }
    if (-not $gitRoot) { $gitRoot = $existingRoot }
    if (-not $short -and $sha -and $sha.Length -ge 7) { $short = $sha.Substring(0, 7) }
    $payload = [ordered]@{
        gitSha           = if ($sha) { "$sha".Trim() } else { 'unknown' }
        gitShaShort      = if ($short) { "$short".Trim() } else { 'unknown' }
        branch           = if ($branch) { "$branch".Trim() } else { 'unknown' }
        repoRoot         = if ($gitRoot) { "$gitRoot".Trim() } else { $repoRoot }
        sourceRoot       = $repoRoot
        dashboardSource  = (Join-Path $repoRoot 'dashboard\index.html')
        desktopDir       = $desktopDir
        pythonSource     = if ($pythonExe) { $pythonExe } else { 'unavailable' }
        compilerSource   = (Join-Path $repoRoot 'tools\scripts')
        mode             = 'dev'
        startedAt        = $started
        provenanceSource = if ($sha) { 'git' } elseif ($existingSha) { 'runtime_build_json' } else { 'unavailable' }
        worktree         = if ($gitRoot) { "$gitRoot".Trim() } else { $repoRoot }
    }
    ($payload | ConvertTo-Json -Depth 4) | Set-Content -Path $outPath -Encoding UTF8
    Write-Host "PROVENANCE: $($payload.gitShaShort) @ $($payload.branch) -> $outPath" -ForegroundColor DarkCyan
}

Write-RuntimeBuildJson

# Prefer python collector when available (adds absolute paths + self-check capability)
if ($pythonExe) {
    $provScript = Join-Path $repoRoot 'tools\scripts\fortna_runtime_provenance.py'
    if (Test-Path $provScript) {
        try {
            & $pythonExe $provScript --repo-root $repoRoot --mode dev --write (Join-Path $desktopDir '.runtime_build.json') 2>$null | Out-Null
        } catch {
            # snapshot from git above is enough
        }
    }
}

Write-Host ''
Write-Host 'START: Site Forge...' -ForegroundColor Cyan
Write-Host ''

npm start
