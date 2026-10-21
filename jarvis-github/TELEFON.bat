@echo off
chcp 65001 >nul
title J.A.R.V.I.S - TELEFONDAN BAGLAN
rem ╔══════════════════════════════════════════════════════════╗
rem ║   J.A.R.V.I.S — TELEFONDAN BAGLAN (bu PC sunucu olur)     ║
rem ║   Cift tikla → telefon icin adres + QR kod cikar.         ║
rem ╚══════════════════════════════════════════════════════════╝
rem
rem Sunucuyu, bilgisayar ajanini ve (acikSA) tuneli baslatir.
rem EXE surumuyle AYNI mantigi kullanir: internet uzerinden erisim
rem config\api_keys.json icindeki "web_remote_access" ile kontrol edilir
rem ve VARSAYILAN OLARAK KAPALIDIR.

set "APP=%~dp0"
if exist "%~dp0sistem\main.py" set "APP=%~dp0sistem\"

set "PY=%APP%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%APP%venv\Scripts\python.exe"

if not exist "%PY%" (
    echo.
    echo Once kurulumu tamamla: BASLAT.bat dosyasina cift tikla.
    echo.
    pause
    exit /b 1
)

"%PY%" "%APP%main.py" --web

echo.
echo JARVIS Web durdu.
pause
