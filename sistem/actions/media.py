"""
Medya oynatma — YouTube, Spotify ve platformun yerlesik muzik uygulamasi.

macOS   → Spotify / Apple Music (AppleScript)
Windows → Spotify (URI + tus simulasyonu) / YouTube

Not: Masaustu uygulamalarinda otomatik oynatma best-effort'tur.
macOS'ta Erisilebilirlik izni gerekebilir.
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.parse
from pathlib import Path

from actions.browser import browser_control
from actions.platform_utils import IS_WIN, open_path, quiet_popen_kwargs


SPOTIFY_APP_MAC = "/Applications/Spotify.app"
MUSIC_APP_MAC = "/System/Applications/Music.app"


# ═══════════════════════════════════════════════════════════════════════════
# Ortak
# ═══════════════════════════════════════════════════════════════════════════
def _play_youtube(query: str) -> str:
    return browser_control("play_youtube", query=query)


def play_media(query: str, provider: str = "auto", autoplay: bool = True) -> str:
    if not query or not query.strip():
        return "Calinacak icerik belirtilmedi."

    normalized_provider = (provider or "auto").strip().lower()
    if normalized_provider in {"yt", "youtube music"}:
        normalized_provider = "youtube"
    elif normalized_provider in {"apple music", "music", "apple_music"}:
        normalized_provider = "apple_music"

    if IS_WIN:
        return _play_media_win(query, normalized_provider, autoplay)
    return _play_media_mac(query, normalized_provider, autoplay)


# ═══════════════════════════════════════════════════════════════════════════
# Windows
# ═══════════════════════════════════════════════════════════════════════════
def _spotify_path_win() -> Path | None:
    """Spotify masaustu kurulumunu arar (klasik veya Store surumu)."""
    candidates = [
        Path(os.environ.get("APPDATA", "")) / "Spotify" / "Spotify.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Spotify" / "Spotify.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "Spotify.exe",
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def _play_media_win(query: str, provider: str, autoplay: bool) -> str:
    if provider == "youtube":
        return _play_youtube(query)

    spotify = _spotify_path_win()

    if provider == "spotify":
        if not spotify:
            return "Spotify yuklu gorunmuyor."
        return _play_spotify_win(query, spotify, autoplay)

    if provider == "apple_music":
        # Windows'ta Apple Music masaustu otomasyonu yok — en yakin karsiligi kullan.
        if spotify:
            result = _play_spotify_win(query, spotify, autoplay)
            return result + " (Windows'ta Apple Music yerine Spotify kullanildi.)"
        return _play_youtube(query) + " (Windows'ta Apple Music yerine YouTube kullanildi.)"

    # auto
    if spotify:
        result = _play_spotify_win(query, spotify, autoplay)
        if "yuklu gorunmuyor" not in result and "acilamadi" not in result:
            return result
    return _play_youtube(query)


# Spotify calmiyorken pencere basligi bunlardan biridir; calarken
# "Sanatci - Sarki" olur. Oynatmayi bu sekilde DOGRULARIZ.
SPOTIFY_IDLE_TITLES = {"spotify", "spotify free", "spotify premium"}


def _spotify_window_title() -> str:
    """Spotify ana penceresinin basligi (yoksa bos string)."""
    try:
        import psutil
        import win32gui
        import win32process
    except ImportError:
        return ""

    spotify_pids = set()
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            if (proc.info["name"] or "").lower() == "spotify.exe":
                spotify_pids.add(proc.info["pid"])
    except Exception:
        return ""
    if not spotify_pids:
        return ""

    found: list[str] = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd) or ""
            if not title.strip():
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in spotify_pids:
                found.append(title.strip())
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        return ""
    return found[0] if found else ""


def _spotify_is_playing() -> bool:
    title = _spotify_window_title()
    return bool(title) and title.strip().lower() not in SPOTIFY_IDLE_TITLES


def _spotify_is_running() -> bool:
    return bool(_spotify_window_title())


def _wait_for_spotify_window(timeout: float) -> bool:
    """Spotify penceresi gorunur olana kadar bekler."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _spotify_is_running():
            return True
        time.sleep(0.4)
    return False


def _focus_spotify() -> bool:
    """
    Spotify penceresini one getirir.

    Tus simulasyonu AKTIF pencereye gider; Spotify onde degilse tuslar
    baska bir uygulamaya giderdi (aramanin hic yazilmamasinin sebebi buydu).
    """
    try:
        import psutil
        import win32con
        import win32gui
        import win32process
    except ImportError:
        return False

    pids = set()
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            if (proc.info["name"] or "").lower() == "spotify.exe":
                pids.add(proc.info["pid"])
    except Exception:
        return False

    target = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if not (win32gui.GetWindowText(hwnd) or "").strip():
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in pids:
                target.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
        if not target:
            return False
        hwnd = target[0]
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


# Spotify'in marka yesili (#1ED760). Arama sonuclarindaki buyuk yuvarlak
# "cal" dugmesi bu renktedir ve ekranda benzersizdir.
SPOTIFY_GREEN_BGR = (96, 215, 30)   # OpenCV BGR sirasi
SPOTIFY_GREEN_TOLERANCE = 26


def _spotify_window_rect() -> "tuple[int, int, int, int] | None":
    try:
        import psutil
        import win32gui
        import win32process
    except ImportError:
        return None

    pids = set()
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            if (proc.info["name"] or "").lower() == "spotify.exe":
                pids.add(proc.info["pid"])
    except Exception:
        return None

    found = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if not (win32gui.GetWindowText(hwnd) or "").strip():
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in pids:
                found.append(win32gui.GetWindowRect(hwnd))
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        return None
    return found[0] if found else None


def _find_spotify_play_button() -> "tuple[int, int] | None":
    """
    Arama sonuclarindaki yesil 'cal' dugmesini rengiyle bulur.

    Neden boyle: Spotify Electron tabanli ve web icerigini Windows'un
    erisilebilirlik agacina acmiyor (UIA'da yalnizca 4 dugme gorunuyor),
    klavye gezinmesi de surumden surume degisiyor. Dugmenin rengi ise sabit.
    """
    rect = _spotify_window_rect()
    if not rect:
        return None
    left, top, right, bottom = rect
    if right - left < 200 or bottom - top < 200:
        return None

    try:
        import cv2
        import numpy as np

        from actions.screen_vision import _ensure_dpi_awareness, _grab_region

        _ensure_dpi_awareness()
        image = _grab_region(left, top, right, bottom)
        frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        target = np.array(SPOTIFY_GREEN_BGR, dtype=np.int16)
        diff = np.abs(frame.astype(np.int16) - target).sum(axis=2)
        mask = (diff <= SPOTIFY_GREEN_TOLERANCE * 3).astype(np.uint8)

        count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
        best = None
        best_area = 0
        for i in range(1, count):
            x, y, w, h, area = stats[i]
            if area < 500 or w < 24 or h < 24 or w > 140 or h > 140:
                continue
            # Yuvarlak dugme → en/boy orani 1'e yakin
            if not (0.75 <= w / float(h) <= 1.33):
                continue
            # Dolgunluk: daire, kendi kutusunun ~%78'ini kaplar
            if area / float(w * h) < 0.55:
                continue
            if area > best_area:
                best_area = area
                best = centroids[i]

        if best is None:
            return None
        return int(left + best[0]), int(top + best[1])
    except Exception:
        return None


def _wait_for_play_button(timeout: float = 6.0) -> "tuple[int, int] | None":
    """
    Yesil 'cal' dugmesi gorunene kadar bekler.

    Spotify arama sonuclarini bazen 1 sn, bazen 5 sn'de ciziyor. Tek seferlik
    arama bu yuzden kararsizdi.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        spot = _find_spotify_play_button()
        if spot:
            return spot
        time.sleep(0.4)
    return None


def _click_screen(x: int, y: int) -> bool:
    """Belirtilen ekran noktasina tiklar, sonra imleci eski yerine koyar."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        old = None
        try:
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            old = (point.x, point.y)
        except Exception:
            old = None

        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.12)
        MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.06)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.1)
        if old:
            user32.SetCursorPos(old[0], old[1])
        return True
    except Exception:
        return False


def _play_spotify_win(query: str, spotify_path: Path, autoplay: bool) -> str:
    encoded_query = urllib.parse.quote(query.strip())
    search_uri = f"spotify:search:{encoded_query}"

    was_running = _spotify_is_running()

    def _send_uri() -> bool:
        ok, _ = open_path(search_uri)
        if ok:
            return True
        try:
            subprocess.Popen([str(spotify_path), "--uri=" + search_uri],
                             **quiet_popen_kwargs())
            return True
        except Exception:
            return False

    if not _send_uri():
        return "Spotify acilamadi."

    # Spotify KAPALIYKEN acilis 10-20 sn surebiliyor. Onceden sabit 3.5 sn
    # bekleniyordu; uygulama daha yuklenmeden tuslar gonderildigi icin arama
    # hic yazilmiyordu. Once pencerenin gerceklesmesini bekle.
    if not _wait_for_spotify_window(timeout=30 if not was_running else 10):
        return "Spotify acildi ama penceresi gorunmedi. Tekrar dener misin?"

    if not was_running:
        # Soguk acilista ilk URI uygulama hazir olmadan gelmis olabilir —
        # pencere olustuktan sonra tekrar gonder, aramaya bu sefer gider.
        time.sleep(3.0)
        _send_uri()

    # Arama sonuclarinin render olmasini bekle
    time.sleep(2.5)

    if not autoplay:
        return f"Spotify icinde '{query}' aramasi acildi."

    # 1) En guvenilir yol: sonuclardaki yesil "cal" dugmesini bulup tikla.
    #    Arama sonuclari degisken surede render oldugu icin dugmeyi TEK SEFER
    #    aramak yerine bir sure BEKLEYEREK ariyoruz; "bazen calisiyor"
    #    sorununun sebebi buydu.
    for attempt in range(3):
        if _focus_spotify():
            time.sleep(0.6)
        spot = _wait_for_play_button(timeout=6.0)
        if not spot:
            time.sleep(1.0)
            continue
        if not _click_screen(*spot):
            continue
        time.sleep(1.8)
        if _spotify_is_playing():
            return f"Spotify'da oynatiliyor: {_spotify_window_title()}"
        # Tiklama tuttu ama calmadi: sayfa henuz oturmamis olabilir, tekrar dene
        time.sleep(1.2)

    # 2) Yedek: klavye gezinmesi.
    # Tuslar AKTIF pencereye gider — Spotify onde degilse baska uygulamaya
    # giderdi. Her denemeden once one getir.
    attempts = (
        [VK_TAB, VK_DOWN, VK_RETURN],   # sonuc listesine gec, ilk satir, cal
        [VK_RETURN],                    # satir zaten odaktaysa dogrudan cal
        [VK_DOWN, VK_RETURN],           # bir satir asagi, cal
    )
    focused_once = False
    for keys in attempts:
        if _focus_spotify():
            focused_once = True
            time.sleep(0.6)
        try:
            _press_keys_win(keys)
        except Exception as exc:
            return (
                f"Spotify aramasi acildi ama otomatik oynatma tamamlanamadi: {exc}. "
                f"Sonuclardan birini secip calabilirsin: {query}"
            )
        time.sleep(1.4)
        if _spotify_is_playing():
            return f"Spotify'da oynatiliyor: {_spotify_window_title()}"

    if not focused_once:
        return (
            f"Spotify'da '{query}' aramasi acildi ama pencere one getirilemedigi "
            "icin oynatilamadi. Spotify'a tiklayip listeden sec."
        )
    return (
        f"Spotify'da '{query}' aramasi acildi ama otomatik oynatmayi "
        "dogrulayamadim. Listeden calmak istedigine tikla."
    )


# Sanal tus kodlari
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SPACE = 0x20
VK_DOWN = 0x28
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_STOP = 0xB2
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1

KEYEVENTF_KEYUP = 0x0002


def _press_keys_win(vk_codes: list[int], delay: float = 0.25) -> None:
    """Sirayla sanal tuslara basar (aktif pencereye gider)."""
    import ctypes

    user32 = ctypes.windll.user32
    for vk in vk_codes:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(delay)


# Kullanicinin soyleyebilecegi ifadeler → standart eylem
_MEDIA_ACTION_ALIASES = {
    "pause": "pause", "duraklat": "pause", "durdur": "pause", "sustur": "pause",
    "beklet": "pause",
    "stop": "stop", "kapat": "stop", "bitir": "stop",
    "resume": "resume", "play": "resume", "devam": "resume", "devam et": "resume",
    "baslat": "resume", "calmaya devam": "resume",
    "play_pause": "play_pause", "toggle": "play_pause",
    "next": "next", "sonraki": "next", "ileri": "next", "gec": "next",
    "previous": "previous", "onceki": "previous", "geri": "previous",
    "prev": "previous",
}


def control_media(action: str = "pause") -> str:
    """
    Calan medyayi kontrol eder (Spotify, YouTube, herhangi bir oynatici).

    Windows'ta klavyenin medya tuslarini tetikler; bu tuslar hangi oynatici
    calisiyorsa ona gider. Spotify aciksa sonuc pencere basligindan
    DOGRULANIR, boylece "durdurdum" derken aslinda durmamis olmayiz.
    """
    key = _MEDIA_ACTION_ALIASES.get((action or "").strip().lower())
    if key is None:
        return (
            f"Bilinmeyen medya eylemi: {action}. "
            "Kullanilabilir: durdur, devam et, sonraki, onceki."
        )

    if IS_WIN:
        return _control_media_win(key)
    return _control_media_mac(key)


def media_key(action: str = "play_pause") -> str:
    """Geriye donuk uyumluluk icin ince sarmalayici."""
    return control_media(action)


def _control_media_win(key: str) -> str:
    spotify_running = _spotify_is_running()
    was_playing = _spotify_is_playing() if spotify_running else None

    # 'pause' ve 'resume' icin play/pause tusu kullanilir; ama medya zaten
    # istenen durumdaysa tusa basmak durumu TERSINE cevirirdi.
    if key == "pause":
        if was_playing is False:
            return "Zaten calan bir sey yok."
        vk, label = VK_MEDIA_PLAY_PAUSE, "duraklatildi"
    elif key == "resume":
        if was_playing is True:
            return f"Zaten caliyor: {_spotify_window_title()}"
        vk, label = VK_MEDIA_PLAY_PAUSE, "devam ettirildi"
    elif key == "stop":
        vk, label = VK_MEDIA_STOP, "durduruldu"
    elif key == "next":
        vk, label = VK_MEDIA_NEXT, "sonraki parcaya gecildi"
    elif key == "previous":
        vk, label = VK_MEDIA_PREV, "onceki parcaya gecildi"
    else:  # play_pause
        vk, label = VK_MEDIA_PLAY_PAUSE, "oynat/duraklat gonderildi"

    try:
        _press_keys_win([vk], delay=0.0)
    except Exception as exc:
        return f"Medya tusu gonderilemedi: {exc}"

    if not spotify_running:
        # Tarayicidaki YouTube gibi durumlarda dogrulayamayiz — dogru olalim
        return f"Medya {label} (calan uygulamaya komut gonderildi)."

    time.sleep(1.0)
    now_playing = _spotify_is_playing()

    if key in ("pause", "stop"):
        if not now_playing:
            return f"Muzik {label}."
        return "Komut gonderildi ama medya hala caliyor gorunuyor."
    if key == "resume":
        if now_playing:
            return f"Muzik {label}: {_spotify_window_title()}"
        return "Komut gonderildi ama medya baslamadi gorunuyor."
    if key in ("next", "previous"):
        title = _spotify_window_title()
        if now_playing and title:
            return f"Simdi caliyor: {title}"
        return f"Medya {label}."
    return f"Medya {label}."


def _control_media_mac(key: str) -> str:
    """macOS: once Spotify/Music'e AppleScript, calisan yoksa bilgilendir."""
    commands = {
        "pause": "pause",
        "stop": "pause",
        "resume": "play",
        "play_pause": "playpause",
        "next": "next track",
        "previous": "previous track",
    }
    command = commands.get(key, "playpause")

    for app_name in ("Spotify", "Music"):
        script = (
            f'if application "{app_name}" is running then\n'
            f'    tell application "{app_name}" to {command}\n'
            f'    return "OK"\n'
            "end if\n"
            'return "NOT_RUNNING"\n'
        )
        ok, detail = _run_osascript(script, timeout=10)
        if ok and "OK" in detail:
            labels = {
                "pause": "duraklatildi", "stop": "durduruldu",
                "resume": "devam ettirildi", "play_pause": "oynat/duraklat gonderildi",
                "next": "sonraki parcaya gecildi", "previous": "onceki parcaya gecildi",
            }
            return f"{app_name}: muzik {labels.get(key, 'komut gonderildi')}."

    return "Calan bir muzik uygulamasi bulunamadi (Spotify veya Music)."


# ═══════════════════════════════════════════════════════════════════════════
# macOS
# ═══════════════════════════════════════════════════════════════════════════
def _run_osascript(script: str, timeout: int = 16) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return False, f"AppleScript calistirilamadi: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or "Bilinmeyen AppleScript hatasi"
        return False, detail

    return True, (result.stdout or "").strip()


def _copy_to_clipboard_mac(text: str) -> tuple[bool, str]:
    try:
        subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=5)
        return True, "ok"
    except Exception as exc:
        return False, f"Panoya kopyalanamadi: {exc}"


def _app_exists(path: str) -> bool:
    return os.path.exists(path)


def _play_media_mac(query: str, provider: str, autoplay: bool) -> str:
    if provider == "spotify":
        return _play_spotify_mac(query, autoplay=autoplay)
    if provider == "apple_music":
        return _play_music_app_mac(query, autoplay=autoplay)
    if provider == "youtube":
        return _play_youtube(query)

    if _app_exists(SPOTIFY_APP_MAC):
        result = _play_spotify_mac(query, autoplay=autoplay)
        if "yüklü görünmüyor" not in result and "açılamadı" not in result:
            return result
    result = _play_music_app_mac(query, autoplay=autoplay)
    if "bulunamadı" not in result:
        return result
    return _play_youtube(query)


def _play_spotify_mac(query: str, autoplay: bool = True) -> str:
    if not _app_exists(SPOTIFY_APP_MAC):
        return "Spotify yüklü görünmüyor."

    encoded_query = urllib.parse.quote(query.strip())
    search_url = f"spotify:search:{encoded_query}"

    try:
        subprocess.run(["open", search_url], check=True, timeout=10)
    except Exception as exc:
        return f"Spotify açılamadı: {exc}"

    if not autoplay:
        return f"Spotify içinde '{query}' araması açıldı."

    script = (
        'tell application "Spotify" to activate\n'
        "delay 1.8\n"
        'tell application "System Events"\n'
        "    key code 48\n"
        "    delay 0.2\n"
        "    key code 125\n"
        "    delay 0.2\n"
        "    key code 36\n"
        "    delay 0.5\n"
        "    key code 49\n"
        "end tell\n"
    )
    ok, detail = _run_osascript(script, timeout=14)
    if ok:
        return f"Spotify'da oynatılıyor: {query}"

    return (
        f"Spotify araması açıldı ama otomatik oynatma tamamlanamadı: {detail}. "
        "Erişilebilirlik izni gerekebilir."
    )


def _play_music_app_mac(query: str, autoplay: bool = True) -> str:
    if not _app_exists(MUSIC_APP_MAC):
        return "Apple Music / Music uygulaması bulunamadı."

    if autoplay:
        escaped_query = query.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'set queryText to "{escaped_query}"\n'
            'tell application "Music"\n'
            "    activate\n"
            "    try\n"
            "        set foundTracks to (search library playlist 1 for queryText only songs)\n"
            "        if (count of foundTracks) > 0 then\n"
            "            set targetTrack to item 1 of foundTracks\n"
            "            play targetTrack\n"
            '            return "PLAYED"\n'
            "        end if\n"
            "    end try\n"
            "end tell\n"
            'return "NOT_FOUND"\n'
        )
        ok, detail = _run_osascript(script, timeout=18)
        if ok and "PLAYED" in detail:
            return f"Music uygulamasında oynatılıyor: {query}"

    ok_clip, detail_clip = _copy_to_clipboard_mac(query.strip())
    if not ok_clip:
        return detail_clip

    script = (
        'tell application "Music" to activate\n'
        "delay 1.0\n"
        'tell application "System Events"\n'
        '    keystroke "f" using {command down}\n'
        "    delay 0.3\n"
        '    keystroke "a" using {command down}\n'
        "    delay 0.1\n"
        '    keystroke "v" using {command down}\n'
        "    delay 1.1\n"
        "    key code 36\n"
        "    delay 0.7\n"
        "    key code 125\n"
        "    delay 0.2\n"
        "    key code 36\n"
        "end tell\n"
    )
    ok, detail = _run_osascript(script, timeout=16)
    if ok:
        if autoplay:
            return f"Music uygulamasında '{query}' için arama yapıldı ve ilk sonuç açıldı."
        return f"Music uygulamasında '{query}' araması açıldı."

    search_url = f"music://music.apple.com/search?term={urllib.parse.quote(query.strip())}"
    try:
        subprocess.run(["open", search_url], check=False, timeout=10)
    except Exception:
        pass
    return (
        f"Music uygulamasında doğrudan oynatma tamamlanamadı: {detail}. "
        f"Arama açıldı: {query}"
    )
