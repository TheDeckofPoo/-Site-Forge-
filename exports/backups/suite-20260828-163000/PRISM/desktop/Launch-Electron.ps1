# Shared Electron launcher for Rockwell Git, Project Intake (EDGAR), and PRISM.
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('git', 'intake', 'prism')]
    [string]$App
)

$ErrorActionPreference = "Stop"

$desktopDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $desktopDir
Set-Location $desktopDir

$appConfig = @{
    git = @{
        Dashboard      = 'index.html'
        Banner         = 'ROCKWELL GIT - Team Branches Dashboard'
        RequirePython  = $false
        RequireTesseract = $false
        PipPackages    = @('lxml')
        VectorReq      = $false
    }
    intake = @{
        Dashboard      = 'project-intake.html'
        Banner         = 'PROJECT INTAKE - EDGAR Pipeline'
        RequirePython  = $true
        RequireTesseract = $true
        PipPackages    = @('pdfplumber', 'pymupdf', 'pandas', 'lxml', 'pillow', 'openpyxl', 'xlrd')
        VectorReq      = $false
    }
    prism = @{
        Dashboard      = 'prism.html'
        Banner         = 'PRISM - Knowledge Engine'
        RequirePython  = $false
        RequireTesseract = $false
        PipPackages    = @()
        VectorReq      = $true
    }
}

$cfg = $appConfig[$App]
$env:ROCKWELL_DASHBOARD = $cfg.Dashboard

function Find-Python {
    foreach ($cmd in @('py', 'python', 'python3')) {
        try {
            $v = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -or ($v -match 'Python')) { return $cmd }
        } catch {}
    }
    return $null
}

function Find-Tesseract {
    $cmd = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        'C:\Program Files\Tesseract-OCR\tesseract.exe',
        'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
    )) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Ensure-Tesseract {
    $tess = Find-Tesseract
    if ($tess) {
        $tessDir = Split-Path -Parent $tess
        if ($env:PATH -notlike "*$tessDir*") {
            $env:PATH = "$tessDir;$env:PATH"
        }
        if (-not $env:TESSDATA_PREFIX) {
            $env:TESSDATA_PREFIX = Join-Path $tessDir 'tessdata'
        }
        Write-Host "OK: Tesseract at $tess" -ForegroundColor Green
        return $true
    }

    Write-Host 'WARN: Tesseract not found (OCR fallback for image-only prints).' -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host 'INSTALL: Tesseract via winget (one-time)...' -ForegroundColor Yellow
        winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements
        $tess = Find-Tesseract
        if ($tess) {
            $tessDir = Split-Path -Parent $tess
            $env:PATH = "$tessDir;$env:PATH"
            $env:TESSDATA_PREFIX = Join-Path $tessDir 'tessdata'
            Write-Host "OK: Tesseract installed at $tess" -ForegroundColor Green
            return $true
        }
    }
    return $false
}

function Ensure-PipPackages {
    param([string]$PythonExe, [string[]]$Packages)

    if (-not $Packages -or $Packages.Count -eq 0) { return }
    Write-Host "INSTALL: Python packages ($($Packages -join ', '))..." -ForegroundColor Yellow
    & $PythonExe -m pip install --upgrade pip *> $null
    & $PythonExe -m pip install $Packages
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: pip install failed. Run: $PythonExe -m pip install $($Packages -join ' ')" -ForegroundColor Red
        pause
        exit 1
    }
    Write-Host 'OK: Python packages ready.' -ForegroundColor Green
}

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host "  $($cfg.Banner)" -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host 'ERROR: npm not found. Install Node.js from https://nodejs.org/' -ForegroundColor Red
    pause
    exit 1
}

$pythonExe = Find-Python
if ($cfg.RequirePython -and -not $pythonExe) {
    Write-Host 'ERROR: Python required. Install from https://python.org/' -ForegroundColor Red
    pause
    exit 1
}

if ($pythonExe) {
    Ensure-PipPackages -PythonExe $pythonExe -Packages $cfg.PipPackages
    if ($cfg.VectorReq) {
        $req = Join-Path $repoRoot 'rockwell-vector-db\requirements.txt'
        if (Test-Path $req) {
            Write-Host 'INSTALL: PRISM vector dependencies...' -ForegroundColor Cyan
            & $pythonExe -m pip install -q -r $req
        }
    }
    if ($cfg.RequireTesseract) {
        Ensure-Tesseract | Out-Null
    }
} elseif ($cfg.PipPackages.Count -gt 0) {
    Write-Host 'WARN: Python not found - some features will be unavailable.' -ForegroundColor Yellow
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

Write-Host ''
Write-Host "START: $($cfg.Banner)..." -ForegroundColor Cyan
Write-Host ''

npm start