"""
Sistem promptunu platforma gore yukler.

core/prompt.txt tek kaynaktir ve macOS diliyle yazilmistir. Windows'ta
calisirken asagidaki degistirme tablosu uygulanir; boylece iki ayri prompt
dosyasini senkron tutmak gerekmez.
"""

from __future__ import annotations

from pathlib import Path

from actions.platform_utils import IS_WIN


from app_paths import resource_path

# Prompt pakete gomulu, salt-okunur bir kaynaktir
BASE_DIR = Path(__file__).resolve().parent
PROMPT_PATH = resource_path("core", "prompt.txt")


# (macOS metni, Windows karsiligi) — sirali uygulanir
WINDOWS_REPLACEMENTS: list[tuple[str, str]] = [
    ("macOS'ta çalışan", "Windows'ta çalışan"),
    ("Apple Calendar takvimini okur", "takvimi okur (Outlook veya JARVIS yerel takvimi)"),
    ("Apple Calendar takvimine yeni etkinlik ekler", "takvime yeni etkinlik ekler"),
    ("Apple Calendar takviminden etkinlik siler", "takvimden etkinlik siler"),
    ("Apple Anımsatıcılar listesini okur", "anımsatıcı listesini okur"),
    ("Apple Anımsatıcılar'a yeni kayıt ekler", "anımsatıcılara yeni kayıt ekler"),
    (
        "play_media: YouTube, Spotify veya Apple Music/Music içinde içerik açar ve mümkünse oynatır",
        "play_media: YouTube veya Spotify içinde içerik açar ve mümkünse oynatır",
    ),
    ("shell_run: Terminal komutu çalıştırır", "shell_run: PowerShell komutu çalıştırır"),
    (
        '- "Masaüstündeki dosyaları listele" → shell_run("ls ~/Desktop")',
        '- "Masaüstündeki dosyaları listele" → shell_run("Get-ChildItem $env:USERPROFILE\\Desktop")',
    ),
    (
        '- "Apple Music\'te Sezen Aksu Gülümse aç" → play_media(query="Sezen Aksu Gülümse", provider="apple_music", autoplay=true)',
        '- "Sezen Aksu Gülümse çal" → play_media(query="Sezen Aksu Gülümse", provider="auto", autoplay=true)',
    ),
]

WINDOWS_NOTE = (
    "\nPLATFORM NOTU (Windows):\n"
    "- Kabuk komutlari PowerShell sozdizimiyle yazilir (ls degil Get-ChildItem, "
    "dosya yollarinda ters bolu).\n"
    "- Takvim ve animsaticilar Outlook yapilandirilmissa Outlook'a, degilse "
    "JARVIS'in kendi yerel takvimine yazilir. Kullanici sormadikca bu ayrimi anlatma.\n"
    "- Apple Music yoktur; muzik istekleri Spotify veya YouTube uzerinden karsilanir.\n"
)

FALLBACK_PROMPT = (
    "Sen JARVIS'sin — {platform}'ta çalışan kişisel AI asistanı. "
    "Türkçe konuş. Kısa ve net yanıtlar ver. "
    "Araçları kullanarak görevleri tamamla, asla taklit etme."
)


def load_system_prompt() -> str:
    """core/prompt.txt icerigini bu platforma uyarlanmis halde dondurur."""
    try:
        text = PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return FALLBACK_PROMPT.format(platform="Windows" if IS_WIN else "macOS")

    return adapt_prompt(text)


def adapt_prompt(text: str) -> str:
    if not IS_WIN:
        return text
    for mac_text, win_text in WINDOWS_REPLACEMENTS:
        text = text.replace(mac_text, win_text)
    return text + WINDOWS_NOTE
