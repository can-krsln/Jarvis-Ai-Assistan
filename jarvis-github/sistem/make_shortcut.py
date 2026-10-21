#!/usr/bin/env python3
"""
JARVIS — Masaustu kisayolu olusturucu
─────────────────────────────────────
macOS   → Masaustune cift tiklanabilir JARVIS.app (.icns ikonlu)
Windows → Masaustune JARVIS.lnk (.ico ikonlu, konsol penceresi acmadan)

Ayrica acilista otomatik baslatma kisayolunu da bu modul yonetir.

Calistirma:
    python make_shortcut.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from actions.platform_utils import IS_WIN, com_context
from app_paths import IS_FROZEN, data_path, resource_path

BASE_DIR = Path(__file__).resolve().parent
# Ikon calisma aninda uretilir → yazilabilir koke
ICON_DIR = data_path("Icon")


def _launch_target() -> tuple[str, str, str]:
    """
    Kisayolun neyi calistiracagi → (hedef, argumanlar, calisma_klasoru).

    .exe olarak paketlendiyse dogrudan exe'yi gosterir; kaynaktan
    calisiyorsa pythonw + main.py.
    """
    if IS_FROZEN:
        exe = Path(sys.executable).resolve()
        return str(exe), "", str(exe.parent)
    return (
        _resolve_python(windowless=True),
        f'"{BASE_DIR / "main.py"}"',
        str(BASE_DIR),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Python yorumlayicisini bul
# ═══════════════════════════════════════════════════════════════════════════
def _venv_dirs() -> list[Path]:
    return [BASE_DIR / ".venv", BASE_DIR / "venv"]


def _resolve_python(windowless: bool = False) -> str:
    """
    Kisayolun JARVIS'i calistiracagi Python — once proje venv'i, yoksa mevcut.
    windowless=True ise Windows'ta pythonw.exe (konsol penceresi acmaz).
    """
    if IS_WIN:
        exe_name = "pythonw.exe" if windowless else "python.exe"
        for venv in _venv_dirs():
            candidate = venv / "Scripts" / exe_name
            if candidate.exists():
                return str(candidate)
        current = Path(sys.executable) if sys.executable else None
        if current and windowless:
            sibling = current.with_name("pythonw.exe")
            if sibling.exists():
                return str(sibling)
        return sys.executable or "python.exe"

    for venv in _venv_dirs():
        candidate = venv / "bin" / "python"
        if candidate.exists():
            return str(candidate)
    return sys.executable or "/usr/bin/python3"


# ═══════════════════════════════════════════════════════════════════════════
# Ikon cizimi — iki platform da ayni gorseli kullanir
# ═══════════════════════════════════════════════════════════════════════════
def _render_icon_image(size: int = 1024):
    """JARVIS ikonunu PIL goruntusu olarak cizer. Pillow yoksa None."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    BG = (2, 12, 12, 255)
    TEAL = (0, 212, 192, 255)
    MID = (0, 100, 90, 255)
    DIM = (4, 40, 36, 255)

    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=190, fill=BG)

    cx, cy, R = size // 2, size // 2 - 40, 300
    for i in range(12):
        alpha = max(0, 180 - i * 14)
        d.ellipse(
            [cx - (R + i * 4), cy - (R + i * 4), cx + (R + i * 4), cy + (R + i * 4)],
            outline=(0, 212, 192, alpha), width=2,
        )
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=DIM, outline=TEAL, width=6)

    try:
        fnt = ImageFont.truetype(str(resource_path("Fonts", "Grift-ExtraBold.ttf")), 380)
    except Exception:
        fnt = ImageFont.load_default()
    bb = d.textbbox((0, 0), "J", font=fnt)
    tx = cx - (bb[2] - bb[0]) // 2 - bb[0]
    ty = cy - (bb[3] - bb[1]) // 2 - bb[1] - 10
    d.text((tx, ty), "J", fill=TEAL, font=fnt)

    try:
        fnt2 = ImageFont.truetype(str(resource_path("Fonts", "Grift-Bold.ttf")), 68)
    except Exception:
        fnt2 = ImageFont.load_default()
    sub = "J.A.R.V.I.S"
    bb2 = d.textbbox((0, 0), sub, font=fnt2)
    d.text((size // 2 - (bb2[2] - bb2[0]) // 2 - bb2[0], size - 170), sub, fill=MID, font=fnt2)

    BL, BW, P = 90, 9, 44
    for bx, by, sx, sy in [(P, P, 1, 1), (size - P, P, -1, 1),
                           (P, size - P, 1, -1), (size - P, size - P, -1, -1)]:
        d.line([bx, by, bx + sx * BL, by], fill=TEAL, width=BW)
        d.line([bx, by, bx, by + sy * BL], fill=TEAL, width=BW)

    return img


def generate_ico() -> "Path | None":
    """Windows .ico ikonu uretir ve kalici bir yola yazar."""
    img = _render_icon_image(1024)
    if img is None:
        return None
    try:
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        ico_path = ICON_DIR / "JARVIS.ico"
        img.save(
            ico_path,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        return ico_path
    except Exception as exc:
        print(f"[Icon] {exc}")
        return None


def generate_icns() -> "Path | None":
    """macOS .icns ikonu uretir (PIL + iconutil)."""
    img = _render_icon_image(1024)
    if img is None:
        return None
    try:
        from PIL import Image

        tmp = Path(tempfile.mkdtemp())
        iconset = tmp / "JARVIS.iconset"
        iconset.mkdir()
        specs = {
            "icon_16x16.png": 16,    "icon_16x16@2x.png": 32,
            "icon_32x32.png": 32,    "icon_32x32@2x.png": 64,
            "icon_128x128.png": 128, "icon_128x128@2x.png": 256,
            "icon_256x256.png": 256, "icon_256x256@2x.png": 512,
            "icon_512x512.png": 512, "icon_512x512@2x.png": 1024,
        }
        for fname, sz in specs.items():
            img.resize((sz, sz), Image.Resampling.LANCZOS).save(iconset / fname)

        icns = tmp / "JARVIS.icns"
        r = subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
                           capture_output=True)
        return icns if r.returncode == 0 else None
    except Exception as exc:
        print(f"[Icon] {exc}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Windows kisayollari
# ═══════════════════════════════════════════════════════════════════════════
def _desktop_dir() -> Path:
    if IS_WIN:
        # OneDrive ile yedeklenen masaustunu de dogru bul
        for env_key in ("OneDrive", "OneDriveConsumer"):
            base = os.environ.get(env_key)
            if base:
                candidate = Path(base) / "Desktop"
                if candidate.is_dir():
                    return candidate
        candidate = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
        if candidate.is_dir():
            return candidate
    return Path.home() / "Desktop"


def startup_dir() -> Path:
    """Windows 'shell:startup' klasoru."""
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _write_windows_shortcut(
    dst: Path,
    target: str,
    arguments: str,
    workdir: str,
    icon: "Path | None",
    description: str = "JARVIS sesli asistan",
) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Asil is ic fonksiyonda yapilir ki COM nesneleri, com_context
    # CoUninitialize cagirmadan once serbest kalsin.
    with com_context():
        _write_shortcut_inner(dst, target, arguments, workdir, icon, description)
    return dst


def _write_shortcut_inner(dst, target, arguments, workdir, icon, description) -> None:
    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(dst))
    shortcut.TargetPath = target
    shortcut.Arguments = arguments
    shortcut.WorkingDirectory = workdir
    shortcut.Description = description
    if icon and Path(icon).exists():
        shortcut.IconLocation = f"{icon},0"
    shortcut.save()


def _create_desktop_shortcut_win() -> Path:
    dst = _desktop_dir() / "JARVIS.lnk"
    icon = generate_ico()
    target, arguments, workdir = _launch_target()
    return _write_windows_shortcut(
        dst, target=target, arguments=arguments, workdir=workdir, icon=icon,
    )


def create_startup_shortcut() -> Path:
    """Acilista otomatik baslatmayi acar."""
    if not IS_WIN:
        raise RuntimeError("Bu fonksiyon yalnizca Windows'ta kullanilir.")
    icon = ICON_DIR / "JARVIS.ico"
    if not icon.exists():
        icon = generate_ico() or icon
    target, arguments, workdir = _launch_target()
    return _write_windows_shortcut(
        startup_dir() / "JARVIS.lnk",
        target=target, arguments=arguments, workdir=workdir, icon=icon,
        description="JARVIS — acilista otomatik baslar",
    )


def remove_startup_shortcut() -> bool:
    path = startup_dir() / "JARVIS.lnk"
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def is_startup_enabled() -> bool:
    return (startup_dir() / "JARVIS.lnk").exists()


# ═══════════════════════════════════════════════════════════════════════════
# macOS kisayolu
# ═══════════════════════════════════════════════════════════════════════════
def _create_desktop_shortcut_mac() -> Path:
    desktop = Path.home() / "Desktop"
    app_dst = desktop / "JARVIS.app"
    python = _resolve_python()

    if app_dst.exists():
        subprocess.run(["rm", "-rf", str(app_dst)], check=False)

    # Kisayol, JARVIS'i Terminal uzerinden acar. Neden?
    # macOS, Downloads/Desktop/Documents klasorlerini korur (TCC). AppleScript'in
    # python'u dogrudan cagirmasi bu klasorlerde sessizce izin hatasi verir.
    # Terminal ise gerekli izin penceresini gosterir → her yerde calisir.
    baslat = BASE_DIR / "BASLAT.command"
    if not baslat.exists():
        baslat = BASE_DIR.parent / "BASLAT.command"
    if baslat.exists():
        script = f'do shell script "open -a Terminal \'{baslat}\'"'
    else:
        script = (
            f'do shell script "\'{python}\' \'{BASE_DIR}/main.py\''
            f' > /tmp/jarvis_launch.log 2>&1 &"'
        )
    res = subprocess.run(["osacompile", "-o", str(app_dst), "-"],
                         input=script, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "osacompile basarisiz")

    icns = generate_icns()
    if icns and icns.exists():
        import plistlib
        import shutil

        res_dir = app_dst / "Contents" / "Resources"
        shutil.copy2(str(icns), str(res_dir / "JARVIS.icns"))
        plist_path = app_dst / "Contents" / "Info.plist"
        try:
            with open(plist_path, "rb") as f:
                pdata = plistlib.load(f)
            pdata["CFBundleIconFile"] = "JARVIS"
            pdata["CFBundleIconName"] = "JARVIS"
            with open(plist_path, "wb") as f:
                plistlib.dump(pdata, f)
        except Exception:
            pass

    return app_dst


def create_desktop_shortcut() -> Path:
    """Masaustunde JARVIS kisayolu olusturur ve yolunu doner."""
    if IS_WIN:
        return _create_desktop_shortcut_win()
    return _create_desktop_shortcut_mac()


if __name__ == "__main__":
    try:
        path = create_desktop_shortcut()
        print(f"✅ Masaustu kisayolu olusturuldu → {path}")
    except Exception as exc:
        print(f"⚠️  Kisayol olusturulamadi: {exc}")
        sys.exit(1)
