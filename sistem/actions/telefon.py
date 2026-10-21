from __future__ import annotations

"""JARVIS telefon kontrolu (Android, adb uzerinden).

PC'ye USB ile bagli ve USB hata ayiklamasi acik telefonu yonetir:
bilgi, durum, uygulama acma, tus/dokunma/kaydirma/yazi, kisi bulma,
ses modlari, ekran suresi, WhatsApp sohbet, arama, kilit acma.
"""

import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

_ADB = None


def adb_yolu():
    global _ADB
    if _ADB:
        return _ADB
    adaylar = [shutil.which("adb")]
    paketler = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    if paketler.is_dir():
        for d in paketler.iterdir():
            a = d / "platform-tools/adb.exe"
            if a.is_file():
                adaylar.append(str(a))
    adaylar += [
        str(Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe"),
        "C:/platform-tools/adb.exe",
    ]
    for a in adaylar:
        if a and Path(a).is_file():
            _ADB = a
            return _ADB
    return ""


def _adb_sifirla():
    adb = adb_yolu()
    if not adb:
        return False
    try:
        subprocess.run([adb, "kill-server"], capture_output=True, timeout=15)
        subprocess.run([adb, "start-server"], capture_output=True, timeout=15)
        return True
    except Exception:
        return False


def _kos(args, timeout=25):
    adb = adb_yolu()
    if not adb:
        return None, "ADB bulunamadi (platform-tools kurulu degil)."
    try:
        p = subprocess.run([adb] + list(args), capture_output=True, timeout=timeout)
        p.stdout = (p.stdout or b"").decode("utf-8", errors="replace")
        p.stderr = (p.stderr or b"").decode("utf-8", errors="replace")
        return p, (p.stdout or "").strip()
    except subprocess.TimeoutExpired:
        if _adb_sifirla():
            try:
                p = subprocess.run([adb] + list(args), capture_output=True, timeout=timeout)
                p.stdout = (p.stdout or b"").decode("utf-8", errors="replace")
                p.stderr = (p.stderr or b"").decode("utf-8", errors="replace")
                return p, (p.stdout or "").strip()
            except subprocess.TimeoutExpired:
                pass
        return None, "HATA: adb zaman asimi (sunucu sifirlandi, telefon cevap vermiyor)."
    except Exception as e:
        return None, "HATA: " + str(e)[:200]


def _cihaz_var():
    _, out = _kos(["devices"])
    if out and bool(re.search(r"\tdevice$", out, re.M)):
        return True
    if _adb_sifirla():
        _, out = _kos(["devices"])
        if out:
            return bool(re.search(r"\tdevice$", out, re.M))
    return False

def _yok():
    return "Telefon bagli degil (USB kablo + USB hata ayiklama izni gerekli)."


def telefon_bilgi():
    """Bagli telefonun kimligi: marka, model, Android surumu, pil, ekran boyutu."""
    if not _cihaz_var():
        return _yok()
    satirlar = []
    _, dev = _kos(["devices"])
    satirlar.append("Cihazlar: " + (dev or "?").replace("\n", " | "))
    for anahtar, etiket in (("ro.product.manufacturer", "Marka"), ("ro.product.model", "Model"),
                            ("ro.build.version.release", "Android")):
        _, v = _kos(["shell", "getprop", anahtar])
        satirlar.append(etiket + ": " + (v or "?"))
    _, pil = _kos(["shell", "dumpsys", "battery"])
    m = re.search(r"level:\s*(\d+)", pil or "")
    satirlar.append("Pil: %" + (m.group(1) if m else "?"))
    _, boy = _kos(["shell", "wm", "size"])
    satirlar.append("Ekran: " + (boy or "?"))
    return "\n".join(satirlar)


def telefon_durum():
    """Anlik durum: ekran (acik/kapali), ses modu, zil/muzik sesi, pil."""
    if not _cihaz_var():
        return _yok()
    satirlar = []
    _, guc = _kos(["shell", "dumpsys", "power"])
    m = re.search(r"mWakefulness=(\w+)", guc or "")
    satirlar.append("Ekran: " + ("acik" if (m and m.group(1) == "Awake") else "kapali"))
    _, zen = _kos(["shell", "settings", "get", "global", "zen_mode"])
    harita = {"0": "normal", "1": "oncelikli", "2": "tam-sessiz", "3": "sadece-alarmlar"}
    satirlar.append("Ses modu: " + harita.get((zen or "").strip(), "?"))
    _, ses = _kos(["shell", "dumpsys", "audio"])
    for akim in ("AUDIO_STREAM_RING", "AUDIO_STREAM_MUSIC"):
        m2 = re.search(re.escape(akim) + r":.*?Current: \S+ \(\S+\): (\d+)", ses or "", re.S)
        if m2:
            satirlar.append(akim.replace("AUDIO_STREAM_", "") + " sesi: " + m2.group(1))
    _, pil = _kos(["shell", "dumpsys", "battery"])
    m3 = re.search(r"level:\s*(\d+)", pil or "")
    satirlar.append("Pil: %" + (m3.group(1) if m3 else "?"))
    return "\n".join(satirlar)


def telefon_uygulama_ac(hedef):
    """Uygulama/ayar/adres acar. Ornek: com.whatsapp | android.settings.SOUND_SETTINGS | https://..."""
    if not _cihaz_var():
        return _yok()
    h = (hedef or "").strip()
    if h.startswith("http"):
        p, _ = _kos(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", h])
    elif h.startswith("android."):
        p, _ = _kos(["shell", "am", "start", "-a", h])
    else:
        p, _ = _kos(["shell", "monkey", "-p", h, "-c", "android.intent.category.LAUNCHER", "1"])
    if p is None:
        return "Acilamadi (adb hatasi)."
    err = (p.stderr or "").strip()
    if p.returncode != 0:
        return "Acilamadi: " + err[:200]
    return "Acildi: " + h


_TUSLAR = {"geri": 4, "back": 4, "ana": 3, "home": 3, "son": 187, "guc": 26, "power": 26,
           "kilit": 26, "sesac": 24, "seskis": 25, "sessiz": 164, "kamera": 27, "enter": 66,
           "sil": 67, "menu": 82, "uyandir": 224}


def telefon_tus(tus):
    """Telefon tusuna basar: geri, ana, guc/kilit, sesac, seskis, kamera, enter, sil, menu."""
    if not _cihaz_var():
        return _yok()
    t = (tus or "").strip().lower()
    kod = _TUSLAR.get(t, t if t.isdigit() else None)
    if kod is None:
        return "Bilinmeyen tus: " + tus
    p, _ = _kos(["shell", "input", "keyevent", str(kod)])
    if p is None:
        return "BasÄ±lamadi (adb hatasi)."
    return "Basildi: " + t


def telefon_dokun(x, y):
    """Ekrana parmakla dokunur (piksel koordinat)."""
    if not _cihaz_var():
        return _yok()
    try:
        p, _ = _kos(["shell", "input", "tap", str(int(x)), str(int(y))])
    except ValueError:
        return "Koordinat sayi olmali."
    if p is None:
        return "Dokunulamadi (adb hatasi)."
    return "Dokunuldu: %s,%s" % (x, y)


def telefon_kaydir(x1, y1, x2, y2, sure="400"):
    """Parmakla kaydirir (piksel koordinat + milisaniye)."""
    if not _cihaz_var():
        return _yok()
    try:
        args = ["shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(sure))]
    except ValueError:
        return "Koordinat ve sure sayi olmali."
    p, _ = _kos(args)
    if p is None:
        return "Kaydirilamadi (adb hatasi)."
    return "Kaydirildi."


def telefon_yaz(metin):
    """Aktif alana metin yazar (once dokunarak alani ac). Turkce karakterler sorunlu olabilir."""
    if not _cihaz_var():
        return _yok()
    m = (metin or "").replace(" ", "%s")
    p, _ = _kos(["shell", "input", "text", m])
    if p is None:
        return "Yazilamadi (adb hatasi)."
    return "Yazildi."


def telefon_kisi_bul(isim):
    """Rehberde isim arar, eslesen kisi + numaralari verir."""
    if not _cihaz_var():
        return _yok()
    _, out = _kos(["shell", "content", "query", "--uri", "content://com.android.contacts/data",
                   "--projection", "display_name", "--projection", "data1"])
    if not out:
        return "Rehber okunamadi."
    hedef = (isim or "").lower()
    degerler = []
    for satir in out.splitlines():
        m = re.search(r"data1=(.*)$", satir)
        if m:
            v = m.group(1).strip()
            if v and v != "NULL":
                degerler.append(v)
    eslesen = []
    son_ad = ""
    for v in degerler:
        rakam = re.sub(r"\D", "", v)
        if len(rakam) >= 7:
            if son_ad and hedef and hedef in son_ad.lower():
                eslesen.append(son_ad + " | " + v)
        else:
            son_ad = v
    eslesen = sorted(set(eslesen))[:20]
    if not eslesen:
        return "Bulunamadi: " + isim
    return "\n".join(eslesen)


def telefon_ses(mod):
    """Ses modu: sessiz (hicbir ses) | sessiz-goster (bildirimler ekrana gelir, sessiz) | normal."""
    if not _cihaz_var():
        return _yok()
    m = (mod or "").strip().lower().replace(" ", "-")
    harita = {"sessiz": "none", "sessiz-goster": "alarms", "normal": "off"}
    if m not in harita:
        return "Mod sessiz | sessiz-goster | normal olmali."
    p, _ = _kos(["shell", "cmd", "notification", "set_dnd", harita[m]])
    if p is None:
        return "Ayarlanamadi (adb hatasi)."
    _, zen = _kos(["shell", "dumpsys", "notification"])
    m2 = re.search(r"mZenMode=(\w+)", zen or "")
    return "Ses modu: " + m + " (" + (m2.group(1) if m2 else "?") + ")"


def telefon_ekran_sure(ms):
    """Ekranin kac milisaniye sonra kapanacagi (ornek: 60000 = 1 dakika)."""
    if not _cihaz_var():
        return _yok()
    try:
        deger = str(int(ms))
    except (ValueError, TypeError):
        return "Sure milisaniye (sayi) olmali."
    p, _ = _kos(["shell", "settings", "put", "system", "screen_off_timeout", deger])
    if p is None:
        return "Ayarlanamadi (adb hatasi)."
    return "Ekran suresi: " + deger + " ms"


def telefon_whatsapp(numara, mesaj=""):
    """WhatsApp sohbetini acar (numara + varsa mesaj onizlemesiyle)."""
    if not _cihaz_var():
        return _yok()
    rakam = re.sub(r"\D", "", numara or "")
    if len(rakam) < 7:
        return "Gecerli numara gerekli."
    adres = "https://wa.me/" + rakam
    if mesaj:
        adres += "?text=" + urllib.parse.quote(mesaj)
    p, _ = _kos(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", adres])
    if p is None:
        return "Acilamadi (adb hatasi)."
    return "WhatsApp acildi: " + rakam


def telefon_ara(hedef):
    """Arama baslatir: numara ya da rehberdeki isim (ornek: Yusuf)."""
    if not _cihaz_var():
        return _yok()
    h = (hedef or "").strip()
    rakam = re.sub(r"\D", "", h)
    if len(rakam) < 7:
        sonuc = telefon_kisi_bul(h)
        if sonuc.startswith("Bulunamadi") or sonuc.startswith("Rehber"):
            return sonuc
        m = re.search(r"[\+\d][\d\s()\-]{5,}", sonuc.splitlines()[0])
        if not m:
            return "Numara cozulemedi: " + h
        rakam = re.sub(r"\D", "", m.group(0))
    p, _ = _kos(["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", "tel:" + rakam])
    if p is None:
        return "Aranamadi (adb hatasi)."
    return "Araniyor: " + rakam


def telefon_kilit_ac(pin):
    """Kilitli ekrani PIN ile acar (once uyandirir, sonra PIN girer)."""
    if not _cihaz_var():
        return _yok()
    _kos(["shell", "input", "keyevent", "224"])
    _, boy = _kos(["shell", "wm", "size"])
    m = re.search(r"(\d+)x(\d+)", boy or "")
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        _kos(["shell", "input", "swipe", str(w // 2), str(int(h * 0.8)), str(w // 2), str(int(h * 0.2))])
    import time
    time.sleep(1)
    _kos(["shell", "input", "text", str(pin or "")])
    _kos(["shell", "input", "keyevent", "66"])
    time.sleep(1)
    _, guc = _kos(["shell", "dumpsys", "power"])
    m2 = re.search(r"mWakefulness=(\w+)", guc or "")
    return "Kilit acma denendi (ekran: " + (m2.group(1) if m2 else "?") + ")."
