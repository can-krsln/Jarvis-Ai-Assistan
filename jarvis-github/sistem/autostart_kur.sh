#!/bin/bash
# JARVIS — macOS Otomatik Başlatma KURULUM
# Kullanım: bash autostart_kur.sh
# Plist'i bu bilgisayara göre dinamik üretir — sabit kullanıcı yolu gömmez.

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_DST="$HOME/Library/LaunchAgents/com.can.jarvis.plist"
PYTHON_BIN="$(command -v python3 || echo /usr/bin/python3)"
PYTHON_DIR="$(dirname "$PYTHON_BIN")"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   J.A.R.V.I.S  Otomatik Başlatma    ║"
echo "╚══════════════════════════════════════╝"
echo ""

# LaunchAgents dizinini oluştur (yoksa)
mkdir -p "$HOME/Library/LaunchAgents"

# Zaten yüklüyse önce kaldır
if launchctl list com.can.jarvis &>/dev/null; then
    echo "⚙️  Önceki servis kaldırılıyor..."
    launchctl unload "$PLIST_DST" 2>/dev/null
fi

# Plist'i bu makineye göre üret
cat > "$PLIST_DST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.can.jarvis</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${BASE_DIR}/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${BASE_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>${BASE_DIR}/jarvis.log</string>
    <key>StandardErrorPath</key>
    <string>${BASE_DIR}/jarvis_error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${PYTHON_DIR}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>
</dict>
</plist>
EOF
echo "✅ Plist üretildi → $PLIST_DST"

# Yükle
launchctl load "$PLIST_DST"
echo "✅ LaunchAgent yüklendi"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║           Kurulum Tamam!             ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "📌 JARVIS artık Mac'e her girişte otomatik açılır."
echo "   Loglar: $BASE_DIR/jarvis.log"
echo ""
echo "⚠️  macOS Sonoma/Ventura'da ilk seferde:"
echo "   Sistem Ayarları → Genel → Oturum Açma Öğeleri"
echo "   → 'JARVIS' öğesini izin ver"
echo ""
echo "🛑 Kaldırmak için: bash autostart_kaldir.sh"
echo ""
