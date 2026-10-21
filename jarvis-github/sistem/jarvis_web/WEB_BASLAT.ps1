# ╔══════════════════════════════════════════════════════════╗
# ║   J.A.R.V.I.S  WEB / TELEFON  —  TEK TIKLA BASLAT         ║
# ║   Sunucu + Windows ajani + (varsa) Cloudflare tuneli      ║
# ╚══════════════════════════════════════════════════════════╝

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$WEB_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT    = Split-Path -Parent $WEB_DIR
Set-Location $WEB_DIR

Clear-Host
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║        J.A.R.V.I.S  WEB  —  Baslatiliyor...              ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Python sec: ana venv (BASLAT'in kurdugu 3.11+) sart ───────
# server.py asyncio.TaskGroup kullanir → 3.11+ gerekir.
$PY = $null
foreach ($cand in @("$ROOT\.venv\Scripts\python.exe", "$ROOT\venv\Scripts\python.exe")) {
    if (Test-Path $cand) {
        & $cand -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $PY = $cand; break }
    }
}
if (-not $PY) {
    Write-Host ""
    Write-Host "Once kurulumu tamamla." -ForegroundColor Yellow
    Write-Host "BASLAT.bat dosyasina cift tikla, sonra tekrar dene."
    Write-Host ""
    Read-Host "Kapatmak icin Enter'a bas"
    exit 1
}

# ── Web bagimliliklari kurulu mu ──────────────────────────────
& $PY -c "import fastapi, uvicorn, websockets" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Web bagimliliklari kuruluyor (bir kerelik)..."
    & $PY -m pip install -q --upgrade pip
    & $PY -m pip install -q -r "$WEB_DIR\requirements.txt" qrcode
}

# ── Surecleri baslat ──────────────────────────────────────────
Write-Host "Sunucu ve Windows ajani baslatiliyor..."
$serverLog = Join-Path $env:TEMP "jarvis_server.log"
$agentLog  = Join-Path $env:TEMP "jarvis_agent.log"
$tunnelLog = Join-Path $env:TEMP "jarvis_tunnel.log"
Remove-Item $serverLog, $agentLog, $tunnelLog -ErrorAction SilentlyContinue

$server = Start-Process -FilePath $PY -ArgumentList "-u", "server.py" `
    -WorkingDirectory $WEB_DIR -RedirectStandardOutput $serverLog `
    -RedirectStandardError "$serverLog.err" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3

$agent = Start-Process -FilePath $PY -ArgumentList "-u", "agent.py" `
    -WorkingDirectory $WEB_DIR -RedirectStandardOutput $agentLog `
    -RedirectStandardError "$agentLog.err" -PassThru -WindowStyle Hidden

# ── cloudflared (tunel) — opsiyonel ───────────────────────────
# Yoksa yerel ag adresi zaten calisir; tunel sadece disaridan
# baglanmak icin gerekir.
$tunnel = $null
$cf = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cf) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "cloudflared kuruluyor (telefon tuneli icin)..."
        winget install --id Cloudflare.cloudflared --scope user `
            --accept-package-agreements --accept-source-agreements `
            --silent --disable-interactivity 2>$null | Out-Null
        # Tek satir olmali: PowerShell satir sonundaki '+' ile devam etmiyor.
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
        $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    }
}
if ($cf) {
    $tunnel = Start-Process -FilePath $cf.Source `
        -ArgumentList "tunnel", "--url", "http://localhost:8765" `
        -RedirectStandardOutput $tunnelLog -RedirectStandardError "$tunnelLog.err" `
        -PassThru -WindowStyle Hidden
}

# ── Tunel URL'ini bekle ───────────────────────────────────────
$URL = ""
if ($tunnel) {
    Write-Host -NoNewline "Genel adres aliniyor"
    for ($i = 0; $i -lt 30; $i++) {
        foreach ($f in @($tunnelLog, "$tunnelLog.err")) {
            if (Test-Path $f) {
                $m = Select-String -Path $f -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" `
                     -AllMatches -ErrorAction SilentlyContinue |
                     Select-Object -First 1
                if ($m) { $URL = $m.Matches[0].Value; break }
            }
        }
        if ($URL) { break }
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 1
    }
    Write-Host ""
}

$TOKEN = & $PY -c "import json;print(json.load(open('web_config.json'))['token'])" 2>$null
$TOKEN = "$TOKEN".Trim()
$LAN = & $PY -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0]);s.close()" 2>$null
$LAN = "$LAN".Trim()

if ($URL) { $FULL = "$URL/?t=$TOKEN" } else { $FULL = "http://${LAN}:8765/?t=$TOKEN" }

# ── Ekrana bas ────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              J.A.R.V.I.S  WEB  —  HAZIR                  ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "TELEFONDAN AC (token gomulu, otomatik baglanir):"
Write-Host ""
Write-Host "   $FULL" -ForegroundColor Cyan
Write-Host ""
& $PY (Join-Path $WEB_DIR "_show_qr.py") $FULL
Write-Host ""
Write-Host "──────────────────────────────────────────────────────────"
Write-Host "TOKEN (elle sorarsa):"
Write-Host ""
Write-Host "        $TOKEN" -ForegroundColor Yellow
Write-Host ""
if (-not $URL) {
    Write-Host "   Not: cloudflared yok — bu adres yalnizca AYNI Wi-Fi agindan calisir."
    Write-Host "   Disaridan baglanmak icin: winget install Cloudflare.cloudflared"
} else {
    Write-Host "   Yerel ag adresi:  http://${LAN}:8765"
}
Write-Host "──────────────────────────────────────────────────────────"
Write-Host "GUVENLIK: Bu adres/QR/token bir SIFRE gibidir — bilgisayarina" -ForegroundColor Red
Write-Host "   tam erisim verir. VIDEODA GOSTERME / kimseyle paylasma." -ForegroundColor Red
Write-Host "   Sifirlamak icin: jarvis_web\web_config.json sil, tekrar baslat."
Write-Host "──────────────────────────────────────────────────────────"
Write-Host ""
Write-Host "Bu pencereyi KAPATMA — kapatinca JARVIS Web durur."
Write-Host "Durdurmak icin:  Ctrl+C"
Write-Host ""

# ── Surecler yasadikca bekle, cikista hepsini temizle ─────────
try {
    while ($true) {
        Start-Sleep -Seconds 2
        if ($server.HasExited) {
            Write-Host "Sunucu durdu. Gunluk: $serverLog" -ForegroundColor Yellow
            break
        }
    }
} finally {
    Write-Host ""
    Write-Host "Kapatiliyor..."
    foreach ($p in @($server, $agent, $tunnel)) {
        if ($p -and -not $p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
