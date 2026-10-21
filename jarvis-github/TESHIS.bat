@echo off
chcp 65001 >nul
title JARVIS — Teshis raporu

:: ============================================================
::  Telefon calismiyorsa bu dosyaya cift tikla. Masaustune
::  "JARVIS_TESHIS.txt" yazar; o dosyayi gonderirsen sorunun
::  nerede oldugu tahmine gerek kalmadan gorulur.
::
::  Sifre, API anahtari veya kisisel dosya TOPLAMAZ.
:: ============================================================

set "OUT=%USERPROFILE%\Desktop\JARVIS_TESHIS.txt"
set "LOGS=%TEMP%\jarvis_web_logs"

echo.
echo   Teshis calisiyor, birkac saniye surer...
echo.

echo ================================================> "%OUT%"
echo  JARVIS TESHIS RAPORU>> "%OUT%"
echo  Tarih: %DATE% %TIME%>> "%OUT%"
echo ================================================>> "%OUT%"
echo.>> "%OUT%"

echo [1] CALISAN JARVIS SURECLERI>> "%OUT%"
tasklist /FI "IMAGENAME eq JARVIS.exe" >> "%OUT%" 2>&1
tasklist /FI "IMAGENAME eq cloudflared.exe" >> "%OUT%" 2>&1
echo.>> "%OUT%"

echo [2] PORTLAR - 8765 sunucu, 8766 telefon https>> "%OUT%"
echo (asagisi BOS ise sunucu hic baslamamis demektir)>> "%OUT%"
netstat -ano | findstr ":8765 :8766" >> "%OUT%" 2>&1
echo.>> "%OUT%"

echo [3] IP ADRESLERI>> "%OUT%"
ipconfig | findstr /C:"IPv4" >> "%OUT%" 2>&1
echo.>> "%OUT%"

echo [4] AG PROFILI - Public/Ortak ise telefon engellenir>> "%OUT%"
powershell -NoProfile -Command "Get-NetConnectionProfile | Select-Object Name,NetworkCategory | Format-Table -AutoSize | Out-String" >> "%OUT%" 2>&1
echo.>> "%OUT%"

echo [5] GUVENLIK DUVARI DURUMU>> "%OUT%"
netsh advfirewall show allprofiles state >> "%OUT%" 2>&1
echo.>> "%OUT%"

echo [6] JARVIS GUVENLIK DUVARI KURALLARI>> "%OUT%"
echo (Action=Block olan varsa telefon SESSIZCE engellenir)>> "%OUT%"
powershell -NoProfile -Command "Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like '*jarvis*' } | Select-Object DisplayName,Direction,Action,Enabled | Format-Table -AutoSize | Out-String" >> "%OUT%" 2>&1
echo.>> "%OUT%"

echo [7] SUNUCU GUNLUGU (server.log)>> "%OUT%"
if exist "%LOGS%\server.log" (
    type "%LOGS%\server.log" >> "%OUT%" 2>&1
) else (
    echo    server.log YOK - telefon hic baslatilmamis>> "%OUT%"
)
echo.>> "%OUT%"

echo [8] TUNEL GUNLUGU - son 25 satir>> "%OUT%"
if exist "%LOGS%\tunnel.log" (
    powershell -NoProfile -Command "Get-Content -LiteralPath $env:TEMP'\jarvis_web_logs\tunnel.log' -Tail 25 | Out-String" >> "%OUT%" 2>&1
) else (
    echo    tunnel.log YOK - tunel hic denenmemis>> "%OUT%"
)
echo.>> "%OUT%"

echo [9] AJAN GUNLUGU - son 15 satir>> "%OUT%"
if exist "%LOGS%\agent.log" (
    powershell -NoProfile -Command "Get-Content -LiteralPath $env:TEMP'\jarvis_web_logs\agent.log' -Tail 15 | Out-String" >> "%OUT%" 2>&1
) else (
    echo    agent.log YOK>> "%OUT%"
)
echo.>> "%OUT%"

echo [10] MASAUSTU JARVIS (pythonw) >> "%OUT%"
tasklist /FI "IMAGENAME eq pythonw.exe" >> "%OUT%" 2>&1
powershell -NoProfile -Command "Get-Process pythonw -ErrorAction SilentlyContinue | Select-Object Id,MainWindowTitle | Format-Table -AutoSize | Out-String" >> "%OUT%" 2>&1
echo.>> "%OUT%"
echo [11] ADB CIHAZLAR >> "%OUT%"
where adb >nul 2>&1 && adb devices >> "%OUT%" 2>&1 || echo adb yok >> "%OUT%"
echo.>> "%OUT%"
echo [12] SPACEDESK >> "%OUT%"
sc query spacedeskService >> "%OUT%" 2>&1
echo.>> "%OUT%"
echo.>> "%OUT%"
echo ================================================>> "%OUT%"
echo  RAPOR SONU>> "%OUT%"
echo ================================================>> "%OUT%"

echo.
echo   Hazir:  %OUT%
echo.
echo   Bu dosyayi gonderirsen sorun hizlica bulunur.
echo.
start "" notepad "%OUT%"
