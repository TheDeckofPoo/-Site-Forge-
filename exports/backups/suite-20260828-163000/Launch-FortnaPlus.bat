@echo off
title FortnaPlus Control (local C:\dev)
cd /d "C:\dev\worktree\FortnaPlus\desktop"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Launch-Electron.ps1"
