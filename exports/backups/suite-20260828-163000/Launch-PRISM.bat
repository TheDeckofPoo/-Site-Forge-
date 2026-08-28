@echo off
title PRISM Knowledge Engine
cd /d "C:\dev\worktree\PRISM\desktop"
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\dev\worktree\PRISM\desktop\Launch-Electron.ps1" -App prism
if errorlevel 1 pause
