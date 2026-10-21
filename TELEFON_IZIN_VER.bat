@echo off
chcp 65001 >nul
title JARVIS — Telefon icin guvenlik duvari izni

:: ============================================================
::  NE ISE YARAR
::  Telefon ayni Wi-Fi uzerinden JARVIS'e baglanirken Windows
::  Guvenlik Duvari gelen baglantiyi engelleyebilir. Bu dosya
::  SADECE 8765-8766 portlarina gelen baglantiya izin verir.
::
::  NE ZAMAN GEREKIR
::  Panelde "guvenlik duvari sorarsa IZIN VER" yaziyorsa ve
::  telefon QR'i okuttugunda sayfa ACILMIYORSA.
::
::  Yonetici izni ister (UAC penceresi cikar) — kural eklemek
::  Windows'ta yonetici yetkisi gerektirir.
:: ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Yonetici izni isteniyor...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo ============================================================
echo   JARVIS — Telefon baglantisi icin guvenlik duvari izni
echo ============================================================
echo.

netsh advfirewall firewall delete rule name="JARVIS Telefon" >nul 2>&1
netsh advfirewall firewall add rule name="JARVIS Telefon" dir=in action=allow protocol=TCP localport=8765-8766 profile=any

if %errorlevel% equ 0 (
    echo.
    echo   [TAMAM] Izin verildi.
    echo   Simdi JARVIS'te TELEFON panelini yeniden baslat ve QR'i okut.
) else (
    echo.
    echo   [HATA] Kural eklenemedi.
    echo   Windows Guvenlik Duvari ayarlarindan JARVIS'e elle izin ver.
)

echo.
echo   Izni geri almak icin:
echo     netsh advfirewall firewall delete rule name="JARVIS Telefon"
echo.
pause
