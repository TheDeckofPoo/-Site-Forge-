@echo off
title FortnaPlus Control
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Electron.ps1"
pause