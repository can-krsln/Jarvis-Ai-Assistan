"""
WhatsApp mesaj gonderme — WhatsApp Desktop veya WhatsApp Web uzerinden.

Desteklenen akislar:
- WhatsApp Desktop'i URL semasiyla numaraya acma
- WhatsApp Desktop icinde kisi adina gore sohbet arama
- WhatsApp Web uzerinden telefon numarasiyla taslak acma
- Sik kullanilan kisileri kalici bellege kaydetme

Kisi/rehber mantigi platformdan bagimsizdir; yalnizca uygulamayi acma ve
tus simulasyonu katmani platforma gore dallanir.

Not: Otomatik gonderim icin macOS'ta Erisilebilirlik izni gerekir.
Windows'ta pencere odagi gerekir.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import unicodedata
import urllib.parse
from pathlib import Path

from memory.memory_manager import load_memory, update_memory
from actions.platform_utils import IS_WIN, open_path, quiet_popen_kwargs


PREFERRED_BROWSERS_MAC = ["Google Chrome", "Safari"]
AUTO_SEND_DELAY_SECONDS = 2.4
WEB_AUTO_SEND_DELAY_SECONDS = 7.0  # WhatsApp Web'in sohbeti yuklemesi zaman alir
from app_paths import data_path

BASE_DIR = Path(__file__).resolve().parent.parent
PHONEBOOK_FILE = data_path("memory", "phone_book.json")


# ═══════════════════════════════════════════════════════════════════════════
# Kisi / rehber — platformdan bagimsiz
# ═══════════════════════════════════════════════════════════════════════════
def _normalize_phone(phone_number: str) -> str:
    digits = re.sub(r"\D+", "", phone_number or "")
    if len(digits) == 11 and digits.startswith("0"):
        digits = "90" + digits[1:]
    elif len(digits) == 10:
        digits = "90" + digits
    if len(digits) < 8 or len(digits) > 15:
        raise ValueError(
            "Telefon numarasi uluslararasi formatta olmali. "
            "Orn: +905551112233"
        )
    return digits


def _normalize_lookup(text: str) -> str:
    text = (text or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i")
    text = re.sub(r"\s+", " ", text)
    return text


def _contact_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _normalize_lookup(name)).strip("_") or "contact"


def _load_contacts() -> dict:
    memory = load_memory()
    contacts = memory.get("whatsapp_contacts", {})
    return contacts if isinstance(contacts, dict) else {}


def _load_phone_book() -> dict:
    try:
        if PHONEBOOK_FILE.exists():
            return json.loads(PHONEBOOK_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_phone_book(phone_book: dict):
    PHONEBOOK_FILE.parent.mkdir(parents=True, exist_ok=True)
    PHONEBOOK_FILE.write_text(
        json.dumps(phone_book, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _contact_candidates() -> list[dict]:
    candidates = []
    for source_name, source in (("whatsapp", _load_contacts()), ("phone_book", _load_phone_book())):
        if not isinstance(source, dict):
            continue
        for key, entry in source.items():
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            item.setdefault("display_name", key)
            item["_source"] = source_name
            item["_key"] = key
            candidates.append(item)
    return candidates


def _match_score(needle: str, candidate: str) -> int:
    candidate_norm = _normalize_lookup(candidate)
    if not candidate_norm:
        return 0
    if candidate_norm == needle:
        return 300
    if candidate_norm.startswith(needle) or needle.startswith(candidate_norm):
        return 220
    if needle in candidate_norm:
        return 160
    needle_parts = needle.split()
    if needle_parts and all(part in candidate_norm for part in needle_parts):
        return 120
    return 0


def _find_contact(recipient_name: str) -> dict | None:
    needle = _normalize_lookup(recipient_name)
    if not needle:
        return None

    best_match = None
    best_score = 0
    for entry in _contact_candidates():
        names = [entry.get("display_name", ""), entry.get("_key", "")]
        aliases = entry.get("aliases", [])
        if isinstance(aliases, list):
            names.extend(str(alias) for alias in aliases)
        elif aliases:
            names.append(str(aliases))

        for name in names:
            score = _match_score(needle, name)
            if score > best_score:
                best_score = score
                best_match = entry

    return best_match


def save_whatsapp_contact(display_name: str, phone_number: str, aliases: str = "") -> str:
    if not display_name or not display_name.strip():
        return "Kisi adi bos olamaz."

    try:
        normalized_phone = _normalize_phone(phone_number)
    except ValueError as exc:
        return str(exc)

    alias_list = []
    if aliases and aliases.strip():
        alias_list = [part.strip() for part in aliases.split(",") if part.strip()]

    key = _contact_key(display_name)
    update_memory(
        {
            "whatsapp_contacts": {
                key: {
                    "value": f"+{normalized_phone}",
                    "display_name": display_name.strip(),
                    "aliases": alias_list,
                }
            }
        }
    )

    if alias_list:
        return f"{display_name.strip()} WhatsApp kisilerine kaydedildi. Takma adlar: {', '.join(alias_list)}"
    return f"{display_name.strip()} WhatsApp kisilerine kaydedildi."


def _unfold_vcf_lines(text: str) -> list[str]:
    unfolded = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def import_phone_book_from_vcf(vcf_path: str) -> str:
    source = Path(vcf_path).expanduser()
    if not source.exists():
        return f"Rehber dosyasi bulunamadi: {source}"

    try:
        text = source.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return f"Rehber dosyasi okunamadi: {exc}"

    entries = {}
    current_lines = []
    imported = 0
    skipped = 0

    def _flush_card(lines: list[str]):
        nonlocal imported, skipped
        if not lines:
            return
        display_name = ""
        aliases = []
        numbers = []
        for line in lines:
            upper = line.upper()
            if upper.startswith("FN:"):
                display_name = line.split(":", 1)[1].strip()
            elif upper.startswith("N:") and not display_name:
                parts = [part.strip() for part in line.split(":", 1)[1].split(";") if part.strip()]
                if parts:
                    display_name = " ".join(reversed(parts[:2])).strip()
            elif "TEL" in upper and ":" in line:
                number = line.split(":", 1)[1].strip()
                if number:
                    numbers.append(number)

        if not display_name or not numbers:
            skipped += 1
            return

        normalized_numbers = []
        for raw_number in numbers:
            try:
                normalized_numbers.append("+" + _normalize_phone(raw_number))
            except ValueError:
                continue
        if not normalized_numbers:
            skipped += 1
            return

        if " " in display_name:
            aliases.extend(part for part in display_name.split() if len(part) > 1)
        key = _contact_key(display_name)
        entries[key] = {
            "display_name": display_name,
            "value": normalized_numbers[0],
            "numbers": normalized_numbers,
            "aliases": sorted({alias for alias in aliases if _normalize_lookup(alias) != _normalize_lookup(display_name)}),
            "source": "vcf_import",
        }
        imported += 1

    for line in _unfold_vcf_lines(text):
        if line.upper() == "BEGIN:VCARD":
            current_lines = []
        elif line.upper() == "END:VCARD":
            _flush_card(current_lines)
            current_lines = []
        else:
            current_lines.append(line)

    phone_book = _load_phone_book()
    phone_book.update(entries)
    _save_phone_book(phone_book)
    return f"{imported} rehber kisisi ice aktarildi, {skipped} kayit atlandi."


# ═══════════════════════════════════════════════════════════════════════════
# Pano ve tus simulasyonu
# ═══════════════════════════════════════════════════════════════════════════
def _copy_to_clipboard(text: str) -> None:
    if IS_WIN:
        _copy_to_clipboard_win(text)
    else:
        subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=5)


def _copy_to_clipboard_win(text: str) -> None:
    import win32clipboard
    import win32con

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_A = 0x41
VK_V = 0x56
VK_F = 0x46
KEYEVENTF_KEYUP = 0x0002


def _press_win(vk: int, delay: float = 0.12) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(delay)


def _press_ctrl_win(vk: int, delay: float = 0.15) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(delay)


# ═══════════════════════════════════════════════════════════════════════════
# macOS yollari
# ═══════════════════════════════════════════════════════════════════════════
def _run_osascript(script: str, timeout: int = 18) -> tuple[bool, str]:
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


def _open_in_browser_mac(url: str) -> str:
    for app_name in PREFERRED_BROWSERS_MAC:
        result = subprocess.run(
            ["open", "-a", app_name, url],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return app_name

    subprocess.run(["open", url], check=False, timeout=10)
    return "default browser"


def _auto_send_mac(app_name: str) -> tuple[bool, str]:
    script = (
        f'delay {AUTO_SEND_DELAY_SECONDS}\n'
        f'tell application "{app_name}" to activate\n'
        "delay 0.3\n"
        'tell application "System Events"\n'
        "    key code 36\n"
        "end tell\n"
    )
    return _run_osascript(script, timeout=12)


def _open_desktop_by_name_mac(recipient_name: str, message: str, send_now: bool) -> tuple[bool, str]:
    try:
        subprocess.run(["open", "-a", "WhatsApp"], check=True, timeout=10)
        _copy_to_clipboard(recipient_name.strip())
    except Exception as exc:
        return False, f"WhatsApp Desktop acilamadi: {exc}"

    search_script = (
        'tell application "WhatsApp" to activate\n'
        "delay 1.1\n"
        'tell application "System Events"\n'
        '    keystroke "f" using {command down}\n'
        "    delay 0.3\n"
        '    keystroke "a" using {command down}\n'
        "    delay 0.1\n"
        '    keystroke "v" using {command down}\n'
        "    delay 1.0\n"
        "    key code 36\n"
        "end tell\n"
    )
    ok, detail = _run_osascript(search_script, timeout=14)
    if not ok:
        return False, detail

    try:
        _copy_to_clipboard(message.strip())
    except Exception as exc:
        return False, f"Mesaj panoya kopyalanamadi: {exc}"

    send_line = "    key code 36\n" if send_now else ""
    message_script = (
        "delay 0.7\n"
        'tell application "WhatsApp" to activate\n'
        "delay 0.2\n"
        'tell application "System Events"\n'
        '    keystroke "v" using {command down}\n'
        "    delay 0.3\n"
        f"{send_line}"
        "end tell\n"
    )
    ok, detail = _run_osascript(message_script, timeout=14)
    if not ok:
        return False, detail

    if send_now:
        return True, f"WhatsApp Desktop uzerinden {recipient_name.strip()} kisisine mesaj gonderildi."
    return True, f"WhatsApp Desktop uzerinden {recipient_name.strip()} icin taslak mesaj acildi."


# ═══════════════════════════════════════════════════════════════════════════
# Windows yollari
# ═══════════════════════════════════════════════════════════════════════════
def whatsapp_desktop_available() -> bool:
    """
    WhatsApp Desktop kurulu mu? (whatsapp: protokolu kayitli mi)

    Not: Microsoft Store surumu protokolu 'shell\\open\\command' ALT ANAHTARI
    OLMADAN kaydeder — UWP aktivasyonu paket manifestinden yurur. Bu yuzden
    olcut, anahtarin 'URL Protocol' degerine sahip olmasidir; boylece hem
    klasik hem Store surumu algilanir.
    """
    if not IS_WIN:
        return Path("/Applications/WhatsApp.app").exists()

    try:
        import winreg
    except ImportError:
        return False

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\Classes\whatsapp") as key:
                try:
                    winreg.QueryValueEx(key, "URL Protocol")
                    return True
                except OSError:
                    # 'URL Protocol' yoksa klasik surumun komut anahtarina bak
                    try:
                        with winreg.OpenKey(root, r"SOFTWARE\Classes\whatsapp\shell\open\command"):
                            return True
                    except OSError:
                        continue
        except OSError:
            continue
    return False


def _open_desktop_via_scheme_win(phone_number: str, message: str) -> tuple[bool, str]:
    encoded_message = urllib.parse.quote(message.strip())
    url = f"whatsapp://send?phone={phone_number}&text={encoded_message}"
    ok, detail = open_path(url)
    if not ok:
        return False, f"WhatsApp Desktop acilamadi: {detail}"
    return True, "WhatsApp Desktop sohbeti acildi."


def _open_desktop_by_name_win(recipient_name: str, message: str, send_now: bool) -> tuple[bool, str]:
    """WhatsApp Desktop'ta kisi adiyla arayip mesaji yazar (best-effort)."""
    ok, detail = open_path("whatsapp://")
    if not ok:
        return False, f"WhatsApp Desktop acilamadi: {detail}"

    # Tuslar aktif pencereye gider — once WhatsApp'i gercekten one getir
    if not _focus_whatsapp():
        return False, "WhatsApp penceresi one getirilemedi"

    try:
        time.sleep(0.8)
        _copy_to_clipboard(recipient_name.strip())
        # Ctrl+F → arama kutusu, yapistir, Enter ile ilk sonucu ac
        _press_ctrl_win(VK_F, delay=0.5)
        _press_ctrl_win(VK_A, delay=0.15)
        _press_ctrl_win(VK_V, delay=1.0)
        _press_win(VK_RETURN, delay=1.0)

        _copy_to_clipboard(message.strip())
        # Sohbette yarim kalmis bir taslak varsa mesaj onun SONUNA eklenirdi.
        # Once tumunu sec ki yapistirma taslagin yerine gecsin.
        _press_ctrl_win(VK_A, delay=0.15)
        _press_ctrl_win(VK_V, delay=0.4)
        if send_now:
            _focus_whatsapp(timeout=4.0)     # odak kaymadigindan emin ol
            _press_win(VK_RETURN, delay=0.3)
    except Exception as exc:
        return False, f"WhatsApp Desktop otomasyonu tamamlanamadi: {exc}"

    if send_now:
        return True, f"WhatsApp Desktop uzerinden {recipient_name.strip()} kisisine mesaj gonderildi."
    return True, f"WhatsApp Desktop uzerinden {recipient_name.strip()} icin taslak mesaj acildi."


def _find_whatsapp_window():
    """Gorunur WhatsApp penceresinin tutamacini bulur."""
    try:
        import win32gui
    except ImportError:
        return None

    found = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = (win32gui.GetWindowText(hwnd) or "").strip()
            if not title or "whatsapp" not in title.lower():
                return True
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if right - left < 300 or bottom - top < 200:
                return True          # bildirim/araç ipucu penceresi
            found.append(((right - left) * (bottom - top), hwnd))
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        return None
    if not found:
        return None
    found.sort(reverse=True)
    return found[0][1]


def _focus_whatsapp(timeout: float = 12.0) -> bool:
    """
    WhatsApp penceresini gercekten ONE getirir ve dogrular.

    Bu adim olmadan Enter tusu o anda odakta olan baska bir uygulamaya
    gidiyordu; mesaj yaziliyor ama gonderilmiyordu.
    """
    try:
        import ctypes

        import win32con
        import win32gui
    except ImportError:
        return False

    user32 = ctypes.windll.user32
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = _find_whatsapp_window()
        if hwnd:
            try:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                # Windows, arka plandaki bir surecin pencere one almasini
                # engelleyebiliyor; ALT dokunusu bu kisitlamayi gevsetir.
                user32.keybd_event(0x12, 0, 0, 0)          # ALT down
                user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.35)
                if win32gui.GetForegroundWindow() == hwnd:
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def _auto_send_win(delay: float) -> tuple[bool, str]:
    try:
        time.sleep(delay)
        if not _focus_whatsapp():
            return False, ("WhatsApp penceresi one getirilemedi, Enter baska "
                           "uygulamaya gidebilirdi — gonderilmedi")
        time.sleep(0.4)
        _press_win(VK_RETURN, delay=0.3)
    except Exception as exc:
        return False, f"Otomatik gonderim tus simulasyonu basarisiz: {exc}"
    return True, "ok"


# ═══════════════════════════════════════════════════════════════════════════
# WhatsApp Web — ortak
# ═══════════════════════════════════════════════════════════════════════════
def _open_whatsapp_web(phone_number: str, message: str) -> tuple[bool, str]:
    encoded_message = urllib.parse.quote(message.strip())
    url = f"https://web.whatsapp.com/send?phone={phone_number}&text={encoded_message}"
    try:
        if IS_WIN:
            ok, detail = open_path(url)
            if not ok:
                return False, f"WhatsApp Web acilamadi: {detail}"
            return True, "varsayilan tarayici"
        app_name = _open_in_browser_mac(url)
    except Exception as exc:
        return False, f"WhatsApp Web acilamadi: {exc}"
    return True, app_name


# ═══════════════════════════════════════════════════════════════════════════
# Ana giris noktasi
# ═══════════════════════════════════════════════════════════════════════════
def send_whatsapp_message(
    message: str,
    phone_number: str = "",
    recipient_name: str = "",
    send_now: bool = False,
    app_target: str = "auto",
) -> str:
    if not message or not message.strip():
        return "Mesaj bos olamaz."

    app_target = (app_target or "auto").strip().lower()
    if app_target not in {"auto", "desktop", "web"}:
        app_target = "auto"

    normalized_phone = ""
    if phone_number and phone_number.strip():
        try:
            normalized_phone = _normalize_phone(phone_number)
        except ValueError as exc:
            return str(exc)

    resolved_name = recipient_name.strip() if recipient_name else ""
    contact = _find_contact(resolved_name) if resolved_name else None

    if contact and not normalized_phone:
        stored_phone = str(contact.get("value", "")).strip()
        try:
            normalized_phone = _normalize_phone(stored_phone)
        except ValueError:
            normalized_phone = ""
        resolved_name = str(contact.get("display_name", resolved_name)).strip() or resolved_name
        contact_source = contact.get("_source", "")
    else:
        contact_source = ""

    if resolved_name and normalized_phone and (contact is None or contact.get("_source") == "phone_book"):
        alias_list = contact.get("aliases", []) if isinstance(contact, dict) else []
        aliases = ", ".join(str(alias) for alias in alias_list) if alias_list else ""
        save_whatsapp_contact(resolved_name, normalized_phone, aliases=aliases)

    desktop_ready = whatsapp_desktop_available()

    # ── Masaustu uygulamasi ──────────────────────────────────────────────
    if app_target in {"auto", "desktop"} and desktop_ready:
        if normalized_phone:
            ok, detail = _open_desktop_via_scheme_win(normalized_phone, message) if IS_WIN \
                else _open_desktop_via_scheme_mac(normalized_phone, message)
            if ok:
                source_note = " (rehberden bulundu)" if contact_source == "phone_book" else ""
                label = resolved_name or f"+{normalized_phone}"
                if not send_now:
                    return f"WhatsApp Desktop icinde {label}{source_note} icin taslak mesaj acildi."
                if IS_WIN:
                    ok_send, send_detail = _auto_send_win(AUTO_SEND_DELAY_SECONDS)
                else:
                    ok_send, send_detail = _auto_send_mac("WhatsApp")
                if ok_send:
                    return f"WhatsApp Desktop uzerinden {label}{source_note} kisisine mesaj gonderildi."
                return (
                    "WhatsApp Desktop sohbeti acildi ama otomatik gonderim tamamlanamadi. "
                    f"{send_detail}. Mesaj kutusu hazir — Enter'a basman yeterli."
                )
            if app_target == "desktop" and not resolved_name:
                return f"WhatsApp Desktop acilirken hata oldu: {detail}"

        if resolved_name:
            ok, detail = _open_desktop_by_name_win(resolved_name, message, send_now) if IS_WIN \
                else _open_desktop_by_name_mac(resolved_name, message, send_now)
            if ok:
                return detail
            if app_target == "desktop":
                return (
                    "WhatsApp Desktop kisi adina gore acilirken hata oldu. "
                    f"{detail}. WhatsApp penceresinin acik ve odakta olmasi gerekir."
                )

    if app_target == "desktop" and not desktop_ready:
        return (
            "WhatsApp Desktop kurulu degil. WhatsApp Web uzerinden gondermek icin "
            "app_target='web' ya da 'auto' kullan."
        )

    # ── WhatsApp Web ─────────────────────────────────────────────────────
    if not normalized_phone:
        if resolved_name:
            return (
                f"'{resolved_name}' icin kayitli bir telefon numarasi bulamadim. "
                "Istersen once kisiyi numarasiyla kaydet."
            )
        return "WhatsApp mesaji icin kisi adi veya telefon numarasi gerekli."

    ok, detail = _open_whatsapp_web(normalized_phone, message)
    if not ok:
        return detail

    label = resolved_name or f"+{normalized_phone}"
    source_note = " (rehberden bulundu)" if contact_source == "phone_book" else ""

    if not send_now:
        return (
            f"WhatsApp sohbeti {detail} icinde {label}{source_note} icin taslak mesajla acildi. "
            "Gondermek icin Enter'a bas."
        )

    if IS_WIN:
        ok_send, send_detail = _auto_send_win(WEB_AUTO_SEND_DELAY_SECONDS)
    else:
        ok_send, send_detail = _auto_send_mac(detail if detail in PREFERRED_BROWSERS_MAC else "Google Chrome")

    if ok_send:
        return f"WhatsApp Web uzerinden {label}{source_note} kisisine mesaj gonderildi."

    return (
        "WhatsApp Web sohbeti acildi ama otomatik gonderim tamamlanamadi. "
        f"{send_detail}. Sohbet hazir — Enter'a basman yeterli."
    )


def _open_desktop_via_scheme_mac(phone_number: str, message: str) -> tuple[bool, str]:
    encoded_message = urllib.parse.quote(message.strip())
    url = f"whatsapp://send?phone={phone_number}&text={encoded_message}"
    try:
        result = subprocess.run(
            ["open", url],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return False, f"WhatsApp Desktop acilamadi: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or "WhatsApp URL scheme acilamadi."
        return False, detail

    return True, "WhatsApp Desktop sohbeti acildi."
