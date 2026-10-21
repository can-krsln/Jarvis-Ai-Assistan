"""
Uygulama acma.

macOS   → 'open -a'
Windows → dogrudan calistirilabilir, Baslat menusu (Get-StartApps) ve
          kisayol taramasi ile uc asamali arama.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess

from actions.platform_utils import IS_WIN, quiet_popen_kwargs, run_powershell


# ── macOS eslemesi ───────────────────────────────────────────────────────────
APP_ALIASES_MAC = {
    "safari":      "Safari",
    "chrome":      "Google Chrome",
    "firefox":     "Firefox",
    "terminal":    "Terminal",
    "iterm":       "iTerm",
    "iterm2":      "iTerm",
    "finder":      "Finder",
    "spotify":     "Spotify",
    "vscode":      "Visual Studio Code",
    "vs code":     "Visual Studio Code",
    "code":        "Visual Studio Code",
    "xcode":       "Xcode",
    "notion":      "Notion",
    "slack":       "Slack",
    "discord":     "Discord",
    "whatsapp":    "WhatsApp",
    "telegram":    "Telegram",
    "zoom":        "zoom.us",
    "mail":        "Mail",
    "calendar":    "Calendar",
    "takvim":      "Calendar",
    "notes":       "Notes",
    "notlar":      "Notes",
    "music":       "Music",
    "müzik":       "Music",
    "photos":      "Photos",
    "fotoğraflar": "Photos",
    "maps":        "Maps",
    "haritalar":   "Maps",
    "calculator":  "Calculator",
    "hesap makinesi": "Calculator",
    "system preferences": "System Preferences",
    "system settings": "System Settings",
    "ayarlar":     "System Settings",
    "activity monitor": "Activity Monitor",
    "aktivite monitörü": "Activity Monitor",
    "preview":     "Preview",
    "önizleme":    "Preview",
    "textedit":    "TextEdit",
    "numbers":     "Numbers",
    "pages":       "Pages",
    "keynote":     "Keynote",
    "figma":       "Figma",
    "postman":     "Postman",
    "docker":      "Docker",
    "sequel pro":  "Sequel Pro",
    "tableplus":   "TablePlus",
}

# ── Windows eslemesi ─────────────────────────────────────────────────────────
# Baslat menusunde aranacak gorunur ad.
APP_ALIASES_WIN = {
    "safari":            "Microsoft Edge",
    "edge":              "Microsoft Edge",
    "chrome":            "Google Chrome",
    "krom":              "Google Chrome",
    "google":            "Google Chrome",
    "fotoşop":           "Photoshop",
    "fotosop":           "Photoshop",
    "photoshop":         "Photoshop",
    "firefox":           "Firefox",
    "opera":             "Opera",
    "brave":             "Brave",
    "terminal":          "Windows Terminal",
    "komut istemi":      "Command Prompt",
    "powershell":        "Windows PowerShell",
    "finder":            "File Explorer",
    "explorer":          "File Explorer",
    "dosya gezgini":     "File Explorer",
    "spotify":           "Spotify",
    "vscode":            "Visual Studio Code",
    "vs code":           "Visual Studio Code",
    "code":              "Visual Studio Code",
    "visual studio":     "Visual Studio",
    "notion":            "Notion",
    "slack":             "Slack",
    "discord":           "Discord",
    "whatsapp":          "WhatsApp",
    "telegram":          "Telegram",
    "zoom":              "Zoom",
    "teams":             "Microsoft Teams",
    "mail":              "Mail",
    "posta":             "Mail",
    "outlook":           "Outlook",
    "calendar":          "Calendar",
    "takvim":            "Calendar",
    "notes":             "Notepad",
    "notlar":            "Notepad",
    "notepad":           "Notepad",
    "not defteri":       "Notepad",
    "sticky notes":      "Sticky Notes",
    "music":             "Media Player",
    "müzik":             "Media Player",
    "photos":            "Photos",
    "fotoğraflar":       "Photos",
    "maps":              "Maps",
    "haritalar":         "Maps",
    "calculator":        "Calculator",
    "hesap makinesi":    "Calculator",
    "settings":          "Settings",
    "ayarlar":           "Settings",
    "system settings":   "Settings",
    "system preferences": "Settings",
    "denetim masası":    "Control Panel",
    "control panel":     "Control Panel",
    "activity monitor":  "Task Manager",
    "aktivite monitörü": "Task Manager",
    "görev yöneticisi":  "Task Manager",
    "task manager":      "Task Manager",
    "preview":           "Photos",
    "önizleme":          "Photos",
    "textedit":          "Notepad",
    "paint":             "Paint",
    "word":              "Word",
    "excel":             "Excel",
    "powerpoint":        "PowerPoint",
    "figma":             "Figma",
    "postman":           "Postman",
    "docker":            "Docker Desktop",
    "steam":             "Steam",
}

# Baslat menusunu beklemeden dogrudan acilabilen hedefler.
DIRECT_TARGETS_WIN = {
    "File Explorer":     "explorer.exe",
    "Notepad":           "notepad.exe",
    "Calculator":        "calc.exe",
    "Paint":             "mspaint.exe",
    "Task Manager":      "taskmgr.exe",
    "Settings":          "ms-settings:",
    "Control Panel":     "control.exe",
    "Command Prompt":    "cmd.exe",
    "Windows PowerShell": "powershell.exe",
    "Maps":              "bingmaps:",
    "Calendar":          "outlookcal:",
    "Mail":              "outlookmail:",
}

_start_apps_cache: list[dict] | None = None


def open_app(app_name: str) -> str:
    """Uygulamayi acar, basari/hata mesaji dondurur."""
    if not app_name:
        return "Uygulama adi belirtilmedi."

    if IS_WIN:
        return _open_app_win(app_name)
    return _open_app_mac(app_name)


# ── macOS ────────────────────────────────────────────────────────────────────
def _open_app_mac(app_name: str) -> str:
    normalized = app_name.lower().strip()
    resolved = APP_ALIASES_MAC.get(normalized, app_name)

    try:
        result = subprocess.run(
            ["open", "-a", resolved],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return f"{resolved} acildi."
        result2 = subprocess.run(
            ["open", resolved],
            capture_output=True, text=True, timeout=10
        )
        if result2.returncode == 0:
            return f"{app_name} acildi."
        return f"'{app_name}' bulunamadi veya acilamadi."
    except subprocess.TimeoutExpired:
        return f"'{app_name}' acilirken zaman asimi."
    except Exception as e:
        return f"Hata: {e}"


# ── Windows ──────────────────────────────────────────────────────────────────
# Turkce harfleri ASCII karsiliklarina indirger — boylece "gorev yoneticisi"
# ile "Görev Yöneticisi" ayni sayilir ve kullanici sapkasiz yazabilir.
_TR_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "I": "i",
    "ş": "s", "Ş": "s",
    "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c",
    "â": "a", "î": "i", "û": "u",
})


def _normalize(text: str) -> str:
    lowered = (text or "").strip().casefold().translate(_TR_FOLD)
    return re.sub(r"\s+", " ", lowered).strip()


def _similarity(a: str, b: str) -> float:
    """0..1 arasi benzerlik — yazim hatalarini tolere etmek icin."""
    return difflib.SequenceMatcher(None, a, b).ratio()


# Takma adlarin sadelestirilmis hali (arama bunun uzerinden yapilir)
_ALIAS_LOOKUP = {_normalize(k): v for k, v in APP_ALIASES_WIN.items()}


def _resolve_alias(app_name: str) -> str:
    """
    Kullanicinin soyledigini bilinen bir uygulama adina cevirir.
    Tam eslesme yoksa yazim hatasina dayanikli yakin eslesme dener
    ("hesep makinasi" → "Calculator").
    """
    needle = _normalize(app_name)
    if not needle:
        return app_name.strip()

    exact = _ALIAS_LOOKUP.get(needle)
    if exact:
        return exact

    best, best_score = None, 0.0
    for alias, target in _ALIAS_LOOKUP.items():
        score = _similarity(needle, alias)
        # Kisa yazimlar icin: "hesap" -> "hesap makinesi"
        if alias.startswith(needle) and len(needle) >= 4:
            score = max(score, 0.9)
        if score > best_score:
            best_score, best = score, target
    if best and best_score >= 0.78:
        return best
    return app_name.strip()


def _open_app_win(app_name: str) -> str:
    raw = (app_name or "").strip()
    needle = _normalize(raw)

    # 1) Kesin takma ad ("hesap makinesi" → Calculator)
    resolved = _ALIAS_LOOKUP.get(needle)

    # 2) Kesin takma ad yoksa ONCE Baslat menusunde yuksek guvenli eslesme ara.
    #    Bu sira onemli: aksi halde "photoshop" bulanik bicimde "Photos"
    #    takma adina kayip yanlis uygulamayi aciyordu.
    if resolved is None:
        app_id, matched_name = _find_start_app(raw, allow_fuzzy=False)
        if app_id and _start_target(f"shell:AppsFolder\\{app_id}", via_explorer=True):
            return f"{matched_name} acildi."
        resolved = _resolve_alias(raw)   # artik bulanik takma ad denenebilir

    # 3) Dogrudan calistirilabilir hedefler
    direct = DIRECT_TARGETS_WIN.get(resolved)
    if direct and _start_target(direct):
        return f"{resolved} acildi."

    # 4) Baslat menusu (masaustu + Store uygulamalari).
    #    Once cozumlenmis Ingilizce ad, sonra kullanicinin soyledigi hali:
    #    Turkce Windows'ta Baslat menusu adlari yereldir ("Hesap Makinesi").
    for candidate_name in (resolved, raw):
        if not candidate_name:
            continue
        app_id, matched_name = _find_start_app(candidate_name)
        if app_id and _start_target(f"shell:AppsFolder\\{app_id}", via_explorer=True):
            return f"{matched_name} acildi."

    # 3) Ad dogrudan bir calistirilabilir olabilir (ornek: "notepad", "chrome")
    candidate = resolved if resolved.lower().endswith(".exe") else f"{resolved}.exe"
    if _start_target(candidate.replace(" ", "")):
        return f"{resolved} acildi."

    return f"'{app_name}' bulunamadi veya acilamadi."


def _start_target(target: str, via_explorer: bool = False) -> bool:
    """Hedefi acar; basarili olursa True."""
    try:
        if via_explorer:
            result = subprocess.run(
                ["explorer.exe", target],
                capture_output=True, text=True, timeout=10,
                **quiet_popen_kwargs(),
            )
            # explorer.exe basarili acilislarda da 1 dondurebilir.
            return result.returncode in (0, 1)
        os.startfile(target)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def _load_start_apps(refresh: bool = False) -> list[dict]:
    """Baslat menusundeki tum uygulamalari (ad + AppID) dondurur."""
    global _start_apps_cache
    if _start_apps_cache is not None and not refresh:
        return _start_apps_cache

    ok, output = run_powershell(
        "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress",
        timeout=25,
    )
    apps: list[dict] = []
    if ok and output:
        try:
            data = json.loads(output)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("Name", "")).strip()
                app_id = str(item.get("AppID", "")).strip()
                if name and app_id:
                    apps.append({"name": name, "app_id": app_id})
        except (json.JSONDecodeError, TypeError):
            pass

    _start_apps_cache = apps
    return apps


def _find_start_app(target_name: str, allow_fuzzy: bool = True) -> tuple[str, str]:
    """
    Baslat menusunde ad eslesmesi → (AppID, gorunen ad).
    allow_fuzzy=False iken yalnizca yuksek guvenli eslesmeler (tam ad, on ek,
    icerme) kabul edilir — yazim hatasi toleransi devre disi.
    """
    needle = _normalize(target_name)
    if not needle:
        return "", ""

    best_score = 0.0
    best: dict | None = None
    for app in _load_start_apps():
        candidate = _normalize(app["name"])
        if not candidate:
            continue

        if candidate == needle:
            score = 300.0
        elif candidate.startswith(needle):
            score = 220.0
        elif needle in candidate:
            score = 160.0
        elif all(part in candidate for part in needle.split()):
            score = 120.0
        elif not allow_fuzzy:
            continue
        else:
            # Yazim hatasi / eksik harf toleransi: "spotfy" → "Spotify",
            # "whatsap" → "WhatsApp", "vs kod" → "Visual Studio Code"
            ratio = _similarity(needle, candidate)
            # Uygulama adinin tek tek kelimeleriyle de karsilastir; boylece
            # "fotosop" uzun "Adobe Photoshop 2024" adini da yakalar
            for word in candidate.split():
                ratio = max(ratio, _similarity(needle, word))
            if ratio < 0.72:
                continue
            score = 60.0 + ratio * 50.0

        # Kisa adlar daha isabetli: "Word" > "Word Viewer Helper"
        score -= min(40.0, len(candidate) / 4.0)
        if score > best_score:
            best_score = score
            best = app

    if best:
        return best["app_id"], best["name"]
    return "", ""
