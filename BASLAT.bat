@echo off
chcp 65001 >nul
title J.A.R.V.I.S
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0BASLAT.ps1"
if errorlevel 1 (
    echo.
    echo JARVIS beklenmedik sekilde kapandi.
    pause
)
