@echo off
chcp 65001 >nul
title J.A.R.V.I.S - TELEFONDAN BAGLAN
rem ╔══════════════════════════════════════════════════════════╗
rem ║   J.A.R.V.I.S — TELEFONDAN BAGLAN (EXE surumu)            ║
rem ║   Cift tikla → telefon icin adres + QR kod cikar.         ║
rem ╚══════════════════════════════════════════════════════════╝
rem
rem JARVIS.exe kendi icinde sunucuyu ve ajani baslatir; Python gerekmez.

if not exist "%~dp0JARVIS.exe" (
    echo.
    echo JARVIS.exe bulunamadi. Bu dosya JARVIS.exe ile ayni klasorde olmali.
    echo.
    pause
    exit /b 1
)

"%~dp0JARVIS.exe" --web

echo.
echo JARVIS Web durdu.
pause
