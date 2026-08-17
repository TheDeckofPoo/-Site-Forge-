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

Write-Host ''
Write-Host 'START: Site Forge...' -ForegroundColor Cyan
Write-Host ''

npm start