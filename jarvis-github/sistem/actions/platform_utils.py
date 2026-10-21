"""
Platform algilama ve ortak yardimcilar.

Tek kod tabani prensibi: her platforma ozel modul bu dosyadaki bayraklarla
dallanir. macOS tarafi bozulmadan Windows destegi eklenir.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path


IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

PLATFORM_LABEL = "Windows" if IS_WIN else ("macOS" if IS_MAC else "Linux")


# ── Konsol penceresi bastirma ────────────────────────────────────────────────
# Windows'ta subprocess her cagrildiginda siyah bir konsol penceresi acilir.
# JARVIS tam ekran bir UI oldugu icin bu bayraklar sart.
if IS_WIN:
    CREATE_NO_WINDOW = 0x08000000
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _STARTUPINFO.wShowWindow = subprocess.SW_HIDE
else:
    CREATE_NO_WINDOW = 0
    _STARTUPINFO = None


def quiet_popen_kwargs() -> dict:
    """subprocess.run/Popen icin konsol penceresini gizleyen ek parametreler."""
    if not IS_WIN:
        return {}
    return {"creationflags": CREATE_NO_WINDOW, "startupinfo": _STARTUPINFO}


def run_quiet(args, timeout: int = 15, **kwargs) -> subprocess.CompletedProcess:
    """Konsol penceresi acmadan komut calistirir."""
    params = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    params.update(quiet_popen_kwargs())
    params.update(kwargs)
    return subprocess.run(args, **params)


# ── PowerShell ───────────────────────────────────────────────────────────────
def run_powershell(script: str, timeout: int = 20) -> tuple[bool, str]:
    """
    PowerShell betigi calistirir → (basarili_mi, cikti).
    Windows disinda cagrilirsa sessizce hata dondurur.
    """
    if not IS_WIN:
        return False, "PowerShell yalnizca Windows'ta kullanilabilir."

    # Turkce karakterlerin bozulmamasi icin cikti kodlamasini UTF-8'e sabitle.
    wrapped = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        "$ErrorActionPreference = 'Continue'; "
    ) + script

    try:
        result = run_quiet(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command", wrapped,
            ],
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, f"PowerShell komutu zaman asimina ugradi ({timeout}s)."
    except Exception as exc:
        return False, f"PowerShell calistirilamadi: {exc}"

    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        return False, output or "PowerShell komutu basarisiz oldu."
    return True, (result.stdout or "").strip()


# ── COM (Outlook, SAPI, kabuk nesneleri) ─────────────────────────────────────
# Aksiyonlar asyncio executor thread'lerinde calisiyor. COM her thread'de
# ayri ayri baslatilmali, yoksa "CoInitialize has not been called" hatasi gelir.
_com_state = threading.local()


@contextmanager
def com_context():
    """Gecerli thread icin COM'u hazirlar; ic ice cagrilara dayaniklidir."""
    if not IS_WIN:
        yield
        return

    try:
        import pythoncom
    except ImportError:
        yield
        return

    depth = getattr(_com_state, "depth", 0)
    if depth == 0:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass
    _com_state.depth = depth + 1
    try:
        yield
    finally:
        _com_state.depth = depth
        if depth == 0:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


# ── Dosya / URL acma ─────────────────────────────────────────────────────────
def open_path(target: str) -> tuple[bool, str]:
    """Bir URL, dosya veya klasoru sistemin varsayilan uygulamasiyla acar."""
    target = (target or "").strip()
    if not target:
        return False, "Acilacak hedef belirtilmedi."

    try:
        if IS_WIN:
            # os.startfile hem URL hem dosya yolu hem de whatsapp:// gibi
            # ozel protokolleri destekler.
            os.startfile(target)  # type: ignore[attr-defined]
            return True, "ok"
        result = run_quiet(["open", target], timeout=10)
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "").strip() or "Acilamadi."
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


class _NullWriter:
    """pythonw.exe altinda konsol yokken print() cagrilarini yutar."""

    encoding = "utf-8"

    def write(self, _data):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False

    def fileno(self):
        raise OSError("konsol yok")


def attach_parent_console() -> bool:
    """
    Penceresiz (GUI) derlenmis .exe'yi, kendisini calistiran konsola baglar.

    JARVIS.exe arayuz uygulamasi oldugu icin konsolsuz derleniyor; bu yuzden
    `JARVIS.exe --web` calistirildiginda adres ve QR kodu HICBIR YERE
    yazilmiyordu. Bu fonksiyon TELEFON.bat'in konsoluna baglanip ciktiyi
    oraya yonlendirir. Konsol yoksa (cift tik) sessizce False doner.
    """
    if not IS_WIN:
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ATTACH_PARENT_PROCESS = -1
        if not kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            return False
        # Kutu cizim karakterleri ve QR icin UTF-8 sart
        try:
            kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass
        for name in ("stdout", "stderr"):
            try:
                stream = open("CONOUT$", "w", encoding="utf-8",
                              errors="replace", buffering=1)
                setattr(sys, name, stream)
            except Exception:
                pass
        return True
    except Exception:
        return False


def configure_console_output() -> None:
    """
    Konsol ciktisini her Windows makinesinde guvenli hale getirir.

    Iki gercek sorunu onler:
    1. Masaustu kisayolu pythonw.exe kullanir → konsol yoktur, sys.stdout None
       olur ve ilk print() AttributeError ile cokerdi.
    2. Turkce Windows'ta yonlendirilmis cikti cp1254'tur; koddaki emojiler
       UnicodeEncodeError firlatirdi.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            setattr(sys, name, _NullWriter())
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_instance_handles: list = []


def acquire_single_instance(name: str = "JARVIS_Desktop_SingleInstance") -> bool:
    """
    Ayni anda tek JARVIS calissin.

    Kisayoldan acilis ~10 sn surdugu icin kullanici sabirsizlanip birkac kez
    tiklayabiliyor; bu da ust uste birden fazla tam ekran pencere aciyordu.
    Ilk ornek True, sonrakiler False alir.
    """
    if not IS_WIN:
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, name)
        ERROR_ALREADY_EXISTS = 183
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
        # Tutamaci canli tut — surec bitene kadar mutex acik kalmali
        _instance_handles.append(handle)
        return True
    except Exception:
        return True


def focus_window(title: str) -> bool:
    """Verilen baslikli pencereyi one getirir."""
    if not IS_WIN:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def user_home() -> Path:
    return Path.home()


def local_app_data() -> Path:
    """Windows'ta %LOCALAPPDATA%, digerlerinde ~/.local/share karsiligi."""
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base)
    return Path.home() / ".local" / "share"
