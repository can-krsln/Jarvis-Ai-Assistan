"""
TTS (Text-to-Speech).

macOS   → yerlesik 'say' komutu (Turkce ses: Yelda)
Windows → SAPI5 (win32com), Turkce ses varsa otomatik secilir

Not: JARVIS'in asil sesi Gemini Live'dan gelir; bu modul yardimci
okuma islevleri icindir.
"""

import subprocess
import threading

from actions.platform_utils import IS_WIN, com_context


# macOS'taki Turkce ses
VOICE_MAC = "Yelda"

# Windows'ta tercih sirasi — ilk eslesen kullanilir
WIN_VOICE_HINTS = ("turkish", "türkçe", "turkce", "tolga", "tr-tr")

MAX_LEN = 500


def speak_text(text: str, on_done=None, blocking: bool = False):
    """
    Metni sesli okur.
    on_done : okuma bitince cagrilacak fonksiyon (opsiyonel)
    blocking: True ise bitene kadar bekler
    """
    if not text or not text.strip():
        if on_done:
            on_done()
        return

    if len(text) > MAX_LEN:
        text = text[:MAX_LEN] + "..."

    def _run():
        try:
            if IS_WIN:
                _speak_win(text)
            else:
                _speak_mac(text)
        except Exception:
            pass
        if on_done:
            on_done()

    if blocking:
        _run()
    else:
        threading.Thread(target=_run, daemon=True).start()


def _speak_mac(text: str):
    try:
        subprocess.run(["say", "-v", VOICE_MAC, text], check=False)
    except FileNotFoundError:
        pass


def _speak_win(text: str):
    # COM her thread'de ayri baslatilmali. Asil is ic fonksiyonda yapilir ki
    # COM nesneleri, com_context CoUninitialize cagirmadan once serbest kalsin.
    with com_context():
        _speak_win_inner(text)


def _speak_win_inner(text: str):
    import win32com.client

    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    voice = _pick_turkish_voice(speaker)
    if voice is not None:
        speaker.Voice = voice
    speaker.Speak(text)


def _pick_turkish_voice(speaker):
    """Kayitli SAPI sesleri icinde Turkce olani bulur; yoksa None."""
    try:
        voices = speaker.GetVoices()
    except Exception:
        return None

    for index in range(voices.Count):
        try:
            item = voices.Item(index)
            description = str(item.GetDescription()).lower()
        except Exception:
            continue
        if any(hint in description for hint in WIN_VOICE_HINTS):
            return item
    return None


def get_available_voices() -> list[str]:
    """Sistemdeki kullanilabilir sesleri listeler."""
    if IS_WIN:
        return _get_available_voices_win()
    return _get_available_voices_mac()


def _get_available_voices_mac() -> list[str]:
    try:
        result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
        voices = []
        for line in result.stdout.splitlines():
            if line.strip():
                voices.append(line.split()[0])
        return voices
    except Exception:
        return []


def _get_available_voices_win() -> list[str]:
    try:
        with com_context():
            return _list_voices_win_inner()
    except Exception:
        return []


def _list_voices_win_inner() -> list[str]:
    import win32com.client

    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    voices = speaker.GetVoices()
    return [str(voices.Item(i).GetDescription()) for i in range(voices.Count)]


def has_turkish_voice() -> bool:
    """Turkce bir ses kurulu mu? Kurulum rehberi icin kullanilir."""
    return any(
        any(hint in name.lower() for hint in WIN_VOICE_HINTS)
        for name in get_available_voices()
    )
