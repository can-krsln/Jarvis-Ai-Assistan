#!/bin/bash
# JARVIS — macOS Otomatik Başlatma KALDIR
# Kullanım: bash autostart_kaldir.sh

PLIST_DST="$HOME/Library/LaunchAgents/com.can.jarvis.plist"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  J.A.R.V.I.S  Otomatik Başlatma     ║"
echo "║         Kaldırılıyor...              ║"
echo "╚══════════════════════════════════════╝"
echo ""

if [ ! -f "$PLIST_DST" ]; then
    echo "ℹ️  Kurulu değil, yapacak bir şey yok."
    exit 0
fi

launchctl unload "$PLIST_DST" 2>/dev/null && echo "✅ LaunchAgent durduruldu"
rm -f "$PLIST_DST" && echo "✅ Plist silindi"

echo ""
echo "✔️  JARVIS artık otomatik açılmayacak."
echo ""
