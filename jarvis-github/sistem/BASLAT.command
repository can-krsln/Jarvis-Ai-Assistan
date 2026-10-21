#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║   J.A.R.V.I.S — TEK TIKLA AÇ (macOS)                      ║
# ║   İlk açılışta kurar, sonra doğrudan başlatır.           ║
# ║   Sadece bu dosyaya çift tıkla — başka dosya gerekmez.   ║
# ╚══════════════════════════════════════════════════════════╝

cd "$(dirname "$0")" || exit 1
ROOT_DIR="$(pwd)"

# Uygulama dosyaları alt klasörde mi (paylaşım düzeni) yoksa yanında mı (dev)?
if [ -f "sistem/main.py" ]; then
    APP_DIR="$ROOT_DIR/sistem"
else
    APP_DIR="$ROOT_DIR"
fi

MIN_MINOR=11
pyver_ok() { "$1" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, $MIN_MINOR) else 1)" 2>/dev/null; }

# ── Kurulu mu? (venv var + Python 3.11+) ─────────────────────
NEED_INSTALL=0
if [ ! -x "$APP_DIR/venv/bin/python" ] || ! pyver_ok "$APP_DIR/venv/bin/python"; then
    NEED_INSTALL=1
fi

# ════════════════════════════════════════════════════════════
#  KURULUM  (yalnızca ilk açılışta veya eksik/eski kurulumda)
# ════════════════════════════════════════════════════════════
if [ "$NEED_INSTALL" = "1" ]; then
    exec > >(tee /tmp/jarvis_kurulum.log) 2>&1
    clear
    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║      J.A.R.V.I.S  İLK KURULUM  —  Lütfen bekleyin        ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""

    # 0) Karantina + izin
    xattr -r -d com.apple.quarantine "$ROOT_DIR" 2>/dev/null || true

    case "$ROOT_DIR" in
        "$HOME/Downloads"/*|"$HOME/Desktop"/*|"$HOME/Documents"/*)
            echo "ℹ️  Not: JARVIS ilk açılışta klasör erişim izni isteyebilir —"
            echo "   çıkan pencerede 'İzin Ver' de."; echo "" ;;
    esac

    # 1) Homebrew
    if ! command -v brew &>/dev/null; then
        echo "📦 Homebrew kuruluyor (bir kerelik)... Mac şifreni isteyebilir."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
    [ -x /usr/local/bin/brew ]    && eval "$(/usr/local/bin/brew shellenv)"

    # 2) Python 3.11+
    find_python() {
        for c in python3.13 python3.12 python3.11 \
                 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
                 /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 \
                 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
            p="$(command -v "$c" 2>/dev/null || true)"; [ -z "$p" ] && p="$c"
            if [ -x "$p" ] && pyver_ok "$p"; then echo "$p"; return 0; fi
        done
        return 1
    }
    PYTHON="$(find_python || true)"
    if [ -z "$PYTHON" ]; then
        echo "📦 Python 3.12 kuruluyor..."
        command -v brew >/dev/null 2>&1 && brew install python@3.12
        PYP="$(brew --prefix python@3.12 2>/dev/null)"
        [ -n "$PYP" ] && [ -x "$PYP/bin/python3.12" ] && PYTHON="$PYP/bin/python3.12"
        [ -z "$PYTHON" ] && PYTHON="$(find_python || true)"
    fi
    if [ -z "$PYTHON" ] || ! pyver_ok "$PYTHON"; then
        echo ""
        echo "❌ Python 3.11+ kurulamadı. https://www.python.org/downloads/ adresinden"
        echo "   Python 3.12'yi kurup bu dosyaya tekrar çift tıkla."
        read -p "Kapatmak için Enter'a bas..."; exit 1
    fi
    echo "✅ Python: $("$PYTHON" --version 2>&1)"

    # 3) PortAudio (mikrofon)
    if ! brew list portaudio &>/dev/null 2>&1; then
        echo "📦 PortAudio kuruluyor..."; brew install portaudio
    fi

    # 4) venv + paketler (uygulama klasöründe)
    cd "$APP_DIR" || exit 1
    [ -d "venv" ] && ! pyver_ok "venv/bin/python" && { echo "♻️  Eski kurulum yenileniyor..."; rm -rf venv; }
    [ ! -d "venv" ] && { echo "📦 Sanal ortam oluşturuluyor..."; "$PYTHON" -m venv venv; }
    source venv/bin/activate
    echo "📦 Paketler yükleniyor (birkaç dakika)..."
    pip install --upgrade pip -q 2>/dev/null
    if ! pip install -r requirements.txt -q; then
        echo ""; echo "❌ Paket kurulumu başarısız. İnternetini kontrol et, tekrar dene."
        echo "   Sorun sürerse /tmp/jarvis_kurulum.log dosyasını Can'e gönder."
        read -p "Kapatmak için Enter'a bas..."; exit 1
    fi

    # 5) Masaüstü kısayolu
    echo "🖥️  Masaüstü kısayolu ekleniyor..."
    python make_shortcut.py 2>/dev/null || true
    echo ""
    echo "✅ Kurulum tamam! JARVIS başlatılıyor..."
    sleep 1
fi

# ════════════════════════════════════════════════════════════
#  BAŞLAT
# ════════════════════════════════════════════════════════════
cd "$APP_DIR" || exit 1
source venv/bin/activate
clear
echo "🚀 JARVIS başlatılıyor..."
python main.py

# JARVIS kapandı → bu Terminal penceresini otomatik kapat
MY_TTY="$(tty)"
osascript >/dev/null 2>&1 <<OSA || true
tell application "Terminal"
    repeat with w in windows
        repeat with t in tabs of w
            try
                if tty of t is "$MY_TTY" then
                    close w
                end if
            end try
        end repeat
    end repeat
end tell
OSA
