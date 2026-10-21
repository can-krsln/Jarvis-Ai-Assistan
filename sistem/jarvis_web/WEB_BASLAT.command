#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║   J.A.R.V.I.S  WEB / TELEFON  —  TEK TIKLA BAŞLAT         ║
# ║   Sunucu + Mac ajanı + Cloudflare tünelini birlikte açar ║
# ╚══════════════════════════════════════════════════════════╝

cd "$(dirname "$0")" || exit 1          # jarvis_web/
ROOT="$(cd .. && pwd)"                   # proje kökü

clear
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║        J.A.R.V.I.S  WEB  —  Başlatılıyor...              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Python seç: ana venv (BASLAT'ın kurduğu 3.11+) şart ──────
# server.py asyncio.TaskGroup kullanır → 3.11+ gerekir. Kurulum yapılmamışsa
# sistem python'una düşüp çökmek yerine kullanıcıyı BASLAT'a yönlendir.
PY="$ROOT/venv/bin/python"
if [ ! -x "$PY" ] || ! "$PY" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)" 2>/dev/null; then
    clear
    echo ""
    echo "⚠️  Önce kurulumu tamamla."
    echo "   BASLAT.command dosyasına çift tıkla, sonra tekrar dene."
    echo ""
    read -p "Kapatmak için Enter'a bas..."
    exit 1
fi

# ── Homebrew yolunu bu oturuma ekle (varsa) ──────────────────
[ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null
[ -x /usr/local/bin/brew ]    && eval "$(/usr/local/bin/brew shellenv)"    2>/dev/null

# ── Web bağımlılıkları kurulu mu ─────────────────────────────
if ! "$PY" -c "import fastapi, uvicorn, websockets" 2>/dev/null; then
    echo "📦 Web bağımlılıkları kuruluyor (bir kerelik)..."
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q -r requirements.txt
fi

# ── cloudflared (tünel) kurulu mu ────────────────────────────
if ! command -v cloudflared >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
        echo "📦 cloudflared kuruluyor (telefon tüneli için)..."
        brew install cloudflared
    else
        echo "❌ cloudflared yok ve Homebrew bulunamadı."
        echo "   https://brew.sh kurup tekrar dene."
        read -p "Kapatmak için Enter..."; exit 1
    fi
fi

# ── qrencode (terminalde QR) — opsiyonel ─────────────────────
if ! command -v qrencode >/dev/null 2>&1 && command -v brew >/dev/null 2>&1; then
    echo "📦 qrencode kuruluyor (QR kod için)..."
    brew install qrencode 2>/dev/null || true
fi

# ── Süreçleri başlat ─────────────────────────────────────────
echo "🚀 Sunucu, Mac ajanı ve tünel başlatılıyor..."
TUNNEL_LOG="/tmp/jarvis_tunnel.log"
: > "$TUNNEL_LOG"

"$PY" -u server.py         > /tmp/jarvis_server.log 2>&1 &  SERVER_PID=$!
sleep 2
"$PY" -u agent.py          > /tmp/jarvis_agent.log  2>&1 &  AGENT_PID=$!
cloudflared tunnel --url http://localhost:8765 > "$TUNNEL_LOG" 2>&1 &  TUNNEL_PID=$!

# Kapatınca hepsini temizle
cleanup() {
    echo ""
    echo "🛑 Kapatılıyor..."
    kill "$SERVER_PID" "$AGENT_PID" "$TUNNEL_PID" 2>/dev/null
    exit 0
}
trap cleanup INT TERM

# ── Tünel URL'ini bekle ──────────────────────────────────────
echo -n "🌐 Genel adres alınıyor"
URL=""
for i in $(seq 1 30); do
    URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$TUNNEL_LOG" | head -1)
    [ -n "$URL" ] && break
    echo -n "."
    sleep 1
done
echo ""

TOKEN=$("$PY" -c "import json;print(json.load(open('web_config.json'))['token'])" 2>/dev/null)

if [ -z "$URL" ]; then
    echo "⚠️  Tünel adresi alınamadı. Yerel ağdan dene: http://localhost:8765"
    FULL="http://localhost:8765/?t=$TOKEN"
else
    FULL="$URL/?t=$TOKEN"
fi

# ── Ekrana bas ───────────────────────────────────────────────
clear
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              J.A.R.V.I.S  WEB  —  HAZIR ✅               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "📱 TELEFONDAN AÇ (token gömülü, otomatik bağlanır):"
echo ""
echo "   $FULL"
echo ""
if command -v qrencode >/dev/null 2>&1; then
    echo "   ▼ Telefon kamerası ile bu QR'ı okut:"
    echo ""
    qrencode -t ANSIUTF8 "$FULL"
    echo ""
fi
echo "──────────────────────────────────────────────────────────"
echo "🔑 TOKEN (elle sorarsa — örn. 'Ana Ekrana Ekle' sonrası):"
echo ""
echo "        $TOKEN"
echo ""
echo "   Adres (tokensiz):  ${URL:-http://localhost:8765}"
echo "──────────────────────────────────────────────────────────"
echo "⚠️  GÜVENLİK: Bu adres/QR/token bir ŞİFRE gibidir — Mac'ine tam"
echo "   erişim verir. VİDEODA GÖSTERME / kimseyle paylaşma."
echo "   Sıfırlamak için:  jarvis_web/web_config.json sil, tekrar başlat."
echo "──────────────────────────────────────────────────────────"
echo ""
echo "Bu pencereyi KAPATMA — kapatınca JARVIS Web durur."
echo "Durdurmak için:  Ctrl+C"
echo ""

# Süreçler yaşadıkça bekle
wait
