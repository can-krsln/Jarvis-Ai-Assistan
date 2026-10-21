"""
Dosya yollari — kaynak (salt-okunur) ve veri (yazilabilir) ayrimi.

Neden gerekli:
Kaynaktan calisirken her sey proje klasorunde durur. Ama PyInstaller ile
.exe'ye paketlendiginde paketin ici SALT OKUNURDUR (onefile modunda her
acilista silinen gecici bir klasore acilir). API anahtari, hafiza, rehber ve
takvim gibi kullanicinin YAZDIGI dosyalar oraya konursa her kapanista kaybolur.

Bu yuzden iki ayri kok var:
  resource_path(...)  → pakete gomulu, salt-okunur (prompt.txt, Fonts, SFX, Icon)
  data_path(...)      → kullanici verisi, yazilabilir (api_keys.json, memory/)

Uc calisma bicimi de desteklenir:
  1. Kaynaktan (python main.py)      → ikisi de proje klasoru
  2. PyInstaller --onedir            → kaynak: _internal, veri: exe'nin yani
  3. PyInstaller --onefile           → kaynak: gecici _MEIPASS, veri: exe'nin yani
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# Kaynaktan calisirken proje kokü bu dosyanin bulundugu klasordur.
PROJECT_DIR = Path(__file__).resolve().parent

IS_FROZEN = bool(getattr(sys, "frozen", False))

APP_NAME = "JARVIS"

_data_dir_cache: Path | None = None


def resource_dir() -> Path:
    """Pakete gomulu salt-okunur dosyalarin kokü."""
    if IS_FROZEN:
        # PyInstaller onefile'da gecici cikarma klasoru, onedir'de _internal
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return PROJECT_DIR


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".jarvis_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def data_dir() -> Path:
    """
    Kullanicinin yazdigi dosyalarin kokü.

    Once exe'nin yanindaki klasor denenir (tasinabilir kullanim: USB'ye at,
    ayarlarin da gelsin). Oraya yazilamiyorsa (ornegin Program Files'a
    kurulmussa) %LOCALAPPDATA%\\JARVIS kullanilir.
    """
    global _data_dir_cache
    if _data_dir_cache is not None:
        return _data_dir_cache

    if not IS_FROZEN:
        _data_dir_cache = PROJECT_DIR
        return _data_dir_cache

    exe_dir = Path(sys.executable).resolve().parent
    if _is_writable(exe_dir):
        _data_dir_cache = exe_dir
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        fallback = Path(base) / APP_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        _data_dir_cache = fallback

    return _data_dir_cache


def resource_path(*parts: str) -> Path:
    return resource_dir().joinpath(*parts)


def data_path(*parts: str) -> Path:
    """Yazilabilir dosya yolu; ust klasoru yoksa olusturur."""
    target = data_dir().joinpath(*parts)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return target


def describe() -> str:
    """Tani amacli — hangi yollarin kullanildigini gosterir."""
    return f"calisma bicimi={run_mode()}\n  kaynak: {resource_dir()}\n  veri  : {data_dir()}"


def run_mode() -> str:
    """'kaynak' | 'exe (klasor)' | 'exe (tek dosya)'"""
    if not IS_FROZEN:
        return "kaynak"
    # PyInstaller 6.x onedir modunda da _MEIPASS ayarlar (exe'nin yanindaki
    # _internal klasoru). Tek dosya modunda ise %TEMP% altinda gecici bir
    # klasordur — ayrimi buradan yapiyoruz.
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return "exe (klasor)"
    exe_dir = Path(sys.executable).resolve().parent
    try:
        if Path(meipass).resolve().parent == exe_dir:
            return "exe (klasor)"
    except Exception:
        pass
    return "exe (tek dosya)"
