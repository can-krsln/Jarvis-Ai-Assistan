#!/usr/bin/env python3
"""
JARVIS Web — Bilgisayar Ajanı
─────────────────────────────
Backend sunucusuna bağlanır ve sistem araçlarını (uygulama açma, takvim,
anımsatıcı, shell, ekran analizi, WhatsApp, medya...) bu bilgisayarda
çalıştırır. macOS ve Windows'ta aynı şekilde çalışır.

Çalıştırma:
    python agent.py                           # localhost'taki sunucuya
    python agent.py --server ws://1.2.3.4:8765 --token <token>

Token verilmezse aynı klasördeki web_config.json'dan okunur.
"""

from __future__ import annotations

import sys

import asyncio
import argparse
import json
import ssl
import traceback
from pathlib import Path

import websockets

# ── Ana proje modüllerine erişim ─────────────────────────────────────────────
WEB_DIR  = Path(__file__).resolve().parent
BASE_DIR = WEB_DIR.parent
sys.path.insert(0, str(BASE_DIR))

from actions.open_app  import open_app
from actions.sys_info  import sys_info
from actions.calendar  import get_calendar_events, add_calendar_event, delete_calendar_event
from actions.reminders import get_reminders, add_reminder
from actions.browser   import browser_control
from actions.shell     import shell_run
from actions.whatsapp  import send_whatsapp_message, save_whatsapp_contact
from actions.media     import play_media, control_media
from actions.screen_vision import analyze_screen
from actions.bilgisayar import tikla, yaz, tus_bas, pencere_odakla, ekran_gor, oge_tikla, aktif_gor, dosya_oku, dosya_yaz, kaydir, surukle, surec_listele, surec_oldur, program_kur, sag_gor, hava_durumu, doviz, pencere_buyut, pencere_kucult, tam_ekrandan_cik, pencere_tasi, dosya_bul
from actions.otogorev import gorev_kur, gorev_listele, gorev_sil, gorev_sonuclari
from actions.spark_kuyruk import spark_cevap_oku
from actions.telefon import (telefon_bilgi, telefon_durum, telefon_uygulama_ac, telefon_tus, telefon_dokun, telefon_kaydir, telefon_yaz, telefon_kisi_bul, telefon_ses, telefon_ekran_sure, telefon_whatsapp, telefon_ara, telefon_kilit_ac)

RECONNECT_DELAY = 3.0


def execute_tool(name: str, args: dict) -> str:
    """Masaüstü main.py'deki araç dağıtımının ajan kopyası (UI'sız)."""
    try:
        if name == "open_app":
            return open_app(args.get("app_name", "")) or \
                   f"{args.get('app_name')} açıldı."

        if name == "sys_info":
            return sys_info(args.get("query", "all")) or "Bilgi alındı."

        if name == "get_calendar_events":
            return get_calendar_events(
                args.get("query", "today"),
                int(args.get("limit", 6) or 6),
            ) or "Takvim bilgisi alindi."

        if name == "add_calendar_event":
            return add_calendar_event(
                args.get("title", ""),
                args.get("start_iso", ""),
                args.get("end_iso", ""),
                args.get("notes", ""),
                args.get("location", ""),
                args.get("calendar_name", ""),
                bool(args.get("all_day", False)),
            ) or "Takvim etkinligi eklendi."

        if name == "delete_calendar_event":
            return delete_calendar_event(
                args.get("title", ""),
                args.get("start_iso", ""),
                args.get("calendar_name", ""),
                bool(args.get("delete_all_matches", False)),
            ) or "Takvim etkinligi silindi."

        if name == "get_reminders":
            return get_reminders(
                args.get("query", "upcoming"),
                int(args.get("limit", 8) or 8),
                args.get("list_name", ""),
            ) or "Animsatici bilgisi alindi."

        if name == "add_reminder":
            return add_reminder(
                args.get("title", ""),
                args.get("due_iso", ""),
                args.get("notes", ""),
                args.get("list_name", ""),
                args.get("priority", ""),
                bool(args.get("all_day", False)),
            ) or "Animsatici eklendi."

        if name == "browser_control":
            return browser_control(
                args.get("action"),
                args.get("url"),
                args.get("query"),
            ) or "Tamam."

        if name == "shell_run":
            return shell_run(args.get("command", "")) or "Komut çalıştırıldı."

        if name == "play_media":
            return play_media(
                args.get("query", ""),
                args.get("provider", "auto"),
                bool(args.get("autoplay", True)),
            ) or "Medya oynatma başlatıldı."

        if name == "control_media":
            return control_media(args.get("action", "pause")) or "Medya komutu gonderildi."


        if name == "analyze_screen":
            return analyze_screen(
                args.get("query", "Ekranda ne var?"),
                args.get("target", "active_window"),
            ) or "Ekran analizi tamamlandi."
        if name == 'ekran_gor':
            return ekran_gor(args.get('soru', 'Ekranda ne var?')) or 'Tamam.'
        if name == 'tikla':
            return tikla(args.get('x', '0'), args.get('y', '0'), args.get('birim', 'piksel'), args.get('tus', 'sol')) or 'Tamam.'
        if name == 'yaz':
            return yaz(args.get('metin', '')) or 'Tamam.'
        if name == 'tus_bas':
            return tus_bas(args.get('tuslar', 'enter')) or 'Tamam.'
        if name == 'pencere_odakla':
            return pencere_odakla(args.get('baslik', '')) or 'Tamam.'
        if name == 'oge_tikla':
            return oge_tikla(args.get('metin', '')) or 'Tamam.'
        if name == 'aktif_gor':
            return aktif_gor(args.get('soru', 'Bu pencerede ne var?')) or 'Tamam.'
        if name == 'dosya_oku':
            return dosya_oku(args.get('yol', ''), args.get('limit', '4000')) or 'Tamam.'
        if name == 'dosya_yaz':
            return dosya_yaz(args.get('yol', ''), args.get('icerik', ''), args.get('ekle', '')) or 'Tamam.'
        if name == 'kaydir':
            return kaydir(args.get('miktar', '-3'), args.get('x'), args.get('y')) or 'Tamam.'
        if name == 'surukle':
            return surukle(args.get('x1', '0'), args.get('y1', '0'), args.get('x2', '0'), args.get('y2', '0'), args.get('birim', 'piksel')) or 'Tamam.'
        if name == 'surec_listele':
            return surec_listele(args.get('filtre', '')) or 'Tamam.'
        if name == 'surec_oldur':
            return surec_oldur(args.get('hedef', '')) or 'Tamam.'
        if name == 'program_kur':
            return program_kur(args.get('paket', '')) or 'Tamam.'
        if name == 'sag_gor':
            return sag_gor(args.get('soru', 'Sag ekranda ne var?')) or 'Tamam.'
        if name == 'hava_durumu':
            return hava_durumu(args.get('sehir', 'Istanbul')) or 'Tamam.'
        if name == 'doviz':
            return doviz(args.get('miktar', '1'), args.get('kaynak', 'USD'), args.get('hedef', 'TRY')) or 'Tamam.'
        if name == 'pencere_buyut':
            return pencere_buyut(args.get('baslik', '')) or 'Tamam.'
        if name == 'pencere_kucult':
            return pencere_kucult(args.get('baslik', '')) or 'Tamam.'
        if name == 'tam_ekrandan_cik':
            return tam_ekrandan_cik() or 'Tamam.'
        if name == 'pencere_tasi':
            return pencere_tasi(args.get('baslik', ''), args.get('hedef', 'sag')) or 'Tamam.'
        if name == 'dosya_bul':
            return dosya_bul(args.get('ad', ''), args.get('surucu', 'C:\\'), args.get('derinlik', 3)) or 'Tamam.'
        if name == 'gorev_kur':
            return gorev_kur(args.get('talimat', ''), args.get('zaman', '')) or 'Tamam.'
        if name == 'gorev_listele':
            return gorev_listele() or 'Tamam.'
        if name == 'gorev_sil':
            return gorev_sil(args.get('hedef', '')) or 'Tamam.'
        if name == 'gorev_sonuclari':
            return gorev_sonuclari(args.get('sayi', '5')) or 'Tamam.'


        if name == "spark_cevap_oku":
            return spark_cevap_oku(args.get("is_id", "")) or "Cevap henuz yazilmamis."

        if name == "send_whatsapp_message":
            return send_whatsapp_message(
                args.get("message", ""),
                args.get("phone_number", ""),
                args.get("recipient_name", ""),
                bool(args.get("send_now", False)),
                args.get("app_target", "auto"),
            ) or "WhatsApp işlemi tamamlandı."

        if name == "save_whatsapp_contact":
            return save_whatsapp_contact(
                args.get("display_name", ""),
                args.get("phone_number", ""),
                args.get("aliases", ""),
            ) or "WhatsApp kişisi kaydedildi."
        if name == 'telefon_bilgi':
            return telefon_bilgi() or 'Tamam.'
        if name == 'telefon_durum':
            return telefon_durum() or 'Tamam.'
        if name == 'telefon_uygulama_ac':
            return telefon_uygulama_ac(args.get('hedef', '')) or 'Tamam.'
        if name == 'telefon_tus':
            return telefon_tus(args.get('tus', '')) or 'Tamam.'
        if name == 'telefon_dokun':
            return telefon_dokun(args.get('x', '0'), args.get('y', '0')) or 'Tamam.'
        if name == 'telefon_kaydir':
            return telefon_kaydir(args.get('x1', '0'), args.get('y1', '0'), args.get('x2', '0'), args.get('y2', '0'), args.get('sure', '400')) or 'Tamam.'
        if name == 'telefon_yaz':
            return telefon_yaz(args.get('metin', '')) or 'Tamam.'
        if name == 'telefon_kisi_bul':
            return telefon_kisi_bul(args.get('isim', '')) or 'Tamam.'
        if name == 'telefon_ses':
            return telefon_ses(args.get('mod', 'normal')) or 'Tamam.'
        if name == 'telefon_ekran_sure':
            return telefon_ekran_sure(args.get('ms', '60000')) or 'Tamam.'
        if name == 'telefon_whatsapp':
            return telefon_whatsapp(args.get('numara', ''), args.get('mesaj', '')) or 'Tamam.'
        if name == 'telefon_ara':
            return telefon_ara(args.get('hedef', '')) or 'Tamam.'
        if name == 'telefon_kilit_ac':
            return telefon_kilit_ac(args.get('pin', '')) or 'Tamam.'

        try:
            from actions.oto_yetenek import oto_dispatch as _oto_dispatch
            return _oto_dispatch(name, args) or 'Tamam.'
        except Exception as _oto_e:
            return 'Hata (oto-yetenek): ' + str(_oto_e)[:200]

    except Exception as e:
        traceback.print_exc()
        return f"Hata: {e}"


async def handle_connection(ws):
    print("[Ajan] ✅ Sunucuya bağlandı — araç çağrıları bekleniyor.")
    loop = asyncio.get_event_loop()

    async def run_call(obj: dict):
        name = obj.get("name", "")
        args = obj.get("args", {}) or {}
        print(f"[Ajan] 🔧 {name} {args}")
        result = await loop.run_in_executor(None, lambda: execute_tool(name, args))
        print(f"[Ajan] 📤 {name} → {str(result)[:80]}")
        await ws.send(json.dumps(
            {"type": "tool_result", "id": obj.get("id", ""), "result": result},
            ensure_ascii=False,
        ))

    async for message in ws:
        try:
            obj = json.loads(message)
        except Exception:
            continue
        if obj.get("type") == "tool_call":
            # Eşzamanlı çağrılar birbirini bloklamasın
            asyncio.create_task(run_call(obj))


def load_token_from_config() -> str:
    # Baslatici token'i ortam degiskeniyle veriyor — dosya yazilamasa bile
    # ajan baglanabilsin diye ONCE buna bakiyoruz.
    import os

    env_token = str(os.environ.get("JARVIS_WEB_TOKEN", "") or "").strip()
    if env_token:
        return env_token

    # Sunucu token'i YAZILABILIR koke yaziyor. .exe'de WEB_DIR paketin
    # icidir (salt okunur) — oradan okursak token'i asla bulamayiz.
    candidates = []
    try:
        from app_paths import data_path

        candidates.append(data_path("jarvis_web", "web_config.json"))
    except Exception:
        pass
    candidates.append(WEB_DIR / "web_config.json")

    for path in candidates:
        try:
            cfg = json.loads(Path(path).read_text(encoding="utf-8"))
            token = str(cfg.get("token", "") or "")
            if token:
                return token
        except Exception:
            continue
    return ""


async def main():
    ap = argparse.ArgumentParser(description="JARVIS bilgisayar ajanı")
    ap.add_argument("--server", default="ws://127.0.0.1:8765",
                    help="Sunucu adresi, örn. wss://1.2.3.4:8765")
    ap.add_argument("--token", default="",
                    help="Erişim token'ı (boşsa web_config.json'dan okunur)")
    args = ap.parse_args()

    token = args.token or load_token_from_config()
    if not token:
        print("[Ajan] ❌ Token bulunamadı. --token verin veya önce sunucuyu çalıştırın.")
        return

    url = f"{args.server.rstrip('/')}/ws/agent?token={token}"

    ssl_ctx = None
    if url.startswith("wss://"):
        # Kendinden imzalı sertifika kabul edilir (v1)
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

    print(f"[Ajan] 🔌 Bağlanılıyor: {args.server}")
    while True:
        try:
            async with websockets.connect(url, ssl=ssl_ctx,
                                          ping_interval=20) as ws:
                await handle_connection(ws)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Ajan] ⚠️  Bağlantı sorunu: {e} — {RECONNECT_DELAY:.0f}s sonra tekrar denenecek.")
        await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Ajan] 👋 Kapatıldı.")
