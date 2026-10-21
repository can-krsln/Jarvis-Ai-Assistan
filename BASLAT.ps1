# ╔══════════════════════════════════════════════════════════╗
# ║   J.A.R.V.I.S — TEK TIKLA AC (Windows)                    ║
# ║   Ilk acilista kurar, sonra dogrudan baslatir.            ║
# ║   BASLAT.bat dosyasina cift tikla — baska islem gerekmez. ║
# ╚══════════════════════════════════════════════════════════╝

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$ROOT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

# Uygulama dosyalari alt klasorde mi (paylasim duzeni) yoksa yaninda mi (dev)?
if (Test-Path (Join-Path $ROOT_DIR "sistem\main.py")) {
    $APP_DIR = Join-Path $ROOT_DIR "sistem"
} else {
    $APP_DIR = $ROOT_DIR
}

$VENV_DIR = Join-Path $APP_DIR ".venv"
$VENV_PY  = Join-Path $VENV_DIR "Scripts\python.exe"
$LOG      = Join-Path $env:TEMP "jarvis_kurulum.log"
$MIN_MINOR = 11

function Test-PyVersion([string]$exe) {
    if (-not $exe) { return $false }
    try {
        & $exe -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, $MIN_MINOR) else 1)" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Find-Python {
    # 1) py launcher — en guvenilir yol
    foreach ($v in @("-3.13", "-3.12", "-3.11", "-3")) {
        try {
            $out = & py $v -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out -and (Test-PyVersion $out)) { return $out.Trim() }
        } catch { }
    }
    # 2) PATH uzerindeki python
    foreach ($name in @("python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and (Test-PyVersion $cmd.Source)) { return $cmd.Source }
    }
    # 3) Bilinen kurulum yollari
    $roots = @("$env:LOCALAPPDATA\Programs\Python", "$env:PROGRAMFILES", "${env:PROGRAMFILES(X86)}", "C:\")
    foreach ($r in $roots) {
        if (-not (Test-Path $r)) { continue }
        $found = Get-ChildItem $r -Filter "Python3*" -Directory -ErrorAction SilentlyContinue |
                 Sort-Object Name -Descending
        foreach ($d in $found) {
            $cand = Join-Path $d.FullName "python.exe"
            if ((Test-Path $cand) -and (Test-PyVersion $cand)) { return $cand }
        }
    }
    return $null
}

# ── Kurulu mu? (venv var + Python 3.11+) ──────────────────────
$NEED_INSTALL = $true
if ((Test-Path $VENV_PY) -and (Test-PyVersion $VENV_PY)) { $NEED_INSTALL = $false }

# ══════════════════════════════════════════════════════════════
#  KURULUM (yalnizca ilk acilista veya eksik/eski kurulumda)
# ══════════════════════════════════════════════════════════════
if ($NEED_INSTALL) {
    Start-Transcript -Path $LOG -Force | Out-Null
    Clear-Host
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║      J.A.R.V.I.S  ILK KURULUM  —  Lutfen bekleyin        ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""

    # 1) Python 3.11+
    $PYTHON = Find-Python
    if (-not $PYTHON) {
        Write-Host "Python 3.11+ bulunamadi. Kuruluyor (bir kerelik)..." -ForegroundColor Yellow
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            winget install --id Python.Python.3.12 --scope user `
                --accept-package-agreements --accept-source-agreements `
                --silent --disable-interactivity
            # Tek satir olmali: PowerShell satir sonundaki '+' ile devam etmiyor.
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
            $PYTHON = Find-Python
        }
    }
    if (-not $PYTHON) {
        Write-Host ""
        Write-Host "Python 3.11+ kurulamadi." -ForegroundColor Red
        Write-Host "https://www.python.org/downloads/ adresinden Python 3.12'yi kur"
        Write-Host "('Add python.exe to PATH' kutusunu ISARETLE) ve BASLAT.bat'a tekrar cift tikla."
        Stop-Transcript | Out-Null
        Read-Host "Kapatmak icin Enter'a bas"
        exit 1
    }
    Write-Host ("Python: " + (& $PYTHON --version 2>&1)) -ForegroundColor Green

    # 2) Sanal ortam
    if ((Test-Path $VENV_DIR) -and -not (Test-PyVersion $VENV_PY)) {
        Write-Host "Eski kurulum yenileniyor..." -ForegroundColor Yellow
        Remove-Item $VENV_DIR -Recurse -Force
    }
    if (-not (Test-Path $VENV_DIR)) {
        Write-Host "Sanal ortam olusturuluyor..."
        & $PYTHON -m venv $VENV_DIR
    }

    # 3) Paketler
    # Not: Windows'ta pyaudio icin hazir wheel var, PortAudio derlemek gerekmez.
    Write-Host "Paketler yukleniyor (birkac dakika)..."
    & $VENV_PY -m pip install --upgrade pip --quiet
    & $VENV_PY -m pip install -r (Join-Path $APP_DIR "requirements.txt") --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Paket kurulumu basarisiz. Internetini kontrol et, tekrar dene." -ForegroundColor Red
        Write-Host "Sorun surerse su dosyayi gonder: $LOG"
        Stop-Transcript | Out-Null
        Read-Host "Kapatmak icin Enter'a bas"
        exit 1
    }

    # 4) Masaustu kisayolu
    Write-Host "Masaustu kisayolu ekleniyor..."
    Push-Location $APP_DIR
    try { & $VENV_PY "make_shortcut.py" } catch { } finally { Pop-Location }

    Write-Host ""
    Write-Host "Kurulum tamam! JARVIS baslatiliyor..." -ForegroundColor Green
    Stop-Transcript | Out-Null
    Start-Sleep -Seconds 1
}

# ══════════════════════════════════════════════════════════════
#  BASLAT
# ══════════════════════════════════════════════════════════════
Set-Location $APP_DIR
Clear-Host
Write-Host "JARVIS baslatiliyor..." -ForegroundColor Cyan
& $VENV_PY "main.py"
