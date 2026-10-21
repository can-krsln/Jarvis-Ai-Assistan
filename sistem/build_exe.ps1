# JARVIS — Windows .exe derleyici
#
# Kullanim:
#   powershell -ExecutionPolicy Bypass -File build_exe.ps1
#   powershell -ExecutionPolicy Bypass -File build_exe.ps1 -Console   # hata ayiklama
#   powershell -ExecutionPolicy Bypass -File build_exe.ps1 -OneFile   # tek dosya
#   powershell -ExecutionPolicy Bypass -File build_exe.ps1 -Clean     # sifirdan
#
# Cikti: dist\JARVIS\JARVIS.exe  (yaninda _internal klasoru ile birlikte)
#
# NOT: Tek dosya (-OneFile) her acilista paketi gecici klasore actigi icin
# baslangici ~10 sn daha yavaslatir. Varsayilan (klasor) surumu onerilir.

param(
    [switch]$Console,
    [switch]$OneFile,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PY   = Join-Path $ROOT ".venv\Scripts\python.exe"

if (-not (Test-Path $PY)) {
    Write-Host "Once BASLAT.bat ile kurulumu tamamla (.venv bulunamadi)." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "J.A.R.V.I.S  —  .exe derleniyor" -ForegroundColor Cyan
Write-Host ""

# PyInstaller kurulu mu
& $PY -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller kuruluyor..."
    & $PY -m pip install --quiet pyinstaller
}

# Uygulama ikonunu uret (exe'ye gomulecek)
Write-Host "Ikon hazirlaniyor..."
& $PY -c "import sys; sys.path.insert(0,r'$ROOT'); from make_shortcut import generate_ico; print(generate_ico())"

# cloudflared — telefondan internet uzerinden baglanmak icin (opsiyonel).
# Depoya konmuyor (51 MB); yoksa resmi Cloudflare surumunden indirilir.
$cf = Join-Path $ROOT "cloudflared.exe"
if (-not (Test-Path $cf)) {
    Write-Host "cloudflared indiriliyor (51 MB, bir kerelik)..."
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 600 `
            -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
            -OutFile $cf
    } catch {
        Write-Host "cloudflared indirilemedi — tunel ozelligi olmadan devam ediliyor." -ForegroundColor Yellow
    }
}
if (Test-Path $cf) {
    $sig = Get-AuthenticodeSignature $cf
    Write-Host ("cloudflared: {0:N0} MB, imza={1}" -f ((Get-Item $cf).Length/1MB), $sig.Status)
    if ($sig.Status -ne "Valid") {
        Write-Host "UYARI: cloudflared imzasi dogrulanamadi, pakete eklenmiyor." -ForegroundColor Red
        Remove-Item $cf -Force
    }
}

if ($Clean) {
    Write-Host "Onceki derleme temizleniyor..."
    foreach ($d in @("$ROOT\build", "$ROOT\dist")) {
        if (Test-Path $d) { Remove-Item $d -Recurse -Force }
    }
}

$env:JARVIS_CONSOLE = if ($Console) { "1" } else { "0" }
$env:JARVIS_ONEFILE = if ($OneFile) { "1" } else { "0" }

Write-Host "PyInstaller calisiyor (birkac dakika surebilir)..."
& $PY -m PyInstaller (Join-Path $ROOT "jarvis.spec") --noconfirm `
      --distpath (Join-Path $ROOT "dist") --workpath (Join-Path $ROOT "build")

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Derleme basarisiz." -ForegroundColor Red
    exit 1
}

$exe = if ($OneFile) { Join-Path $ROOT "dist\JARVIS.exe" } else { Join-Path $ROOT "dist\JARVIS\JARVIS.exe" }
if (-not (Test-Path $exe)) {
    Write-Host "Beklenen cikti bulunamadi: $exe" -ForegroundColor Red
    exit 1
}

$outDir = Split-Path -Parent $exe
$size = (Get-ChildItem $outDir -Recurse -File | Measure-Object Length -Sum).Sum

Write-Host ""
Write-Host "Hazir." -ForegroundColor Green
Write-Host "  exe    : $exe"
Write-Host ("  boyut  : {0:N0} MB" -f ($size / 1MB))
Write-Host ""
Write-Host "Paylasilabilir paket icin: hazirla_paylasim.ps1 -Mode exe"
