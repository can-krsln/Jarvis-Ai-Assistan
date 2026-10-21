from __future__ import annotations

"""Otomatik gorevler: JARVIS'in KENDI kurdugu periyodik isler.

Kullanici "her sabah 8'de havayi soyle" dediginde model gorev_kur'u cagirir;
zaman ifadesi burada yapisal hale cevrilip config/otogorev.json'a yazilir.
sistem/otogorev_kos.py (Gorev Zamanlayici'da 5 dakikada bir) vadesi gelenleri
calistirir, sonucu kuyruk/otogorev-sonuc.jsonl'ye yazar.

Guvenlik: gorevler SADECE bu bilgisayarin sahibinin sozuyle kurulur/silinir.
"""

import json
import re
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOSYA = BASE_DIR / "config" / "otogorev.json"
SONUC_DOSYA = BASE_DIR / "kuyruk" / "otogorev-sonuc.jsonl"

GUNLER = {
    "pazartesi": 0, "sali": 1, "salı": 1, "carsamba": 2, "çarşamba": 2,
    "persembe": 3, "perşembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6,
}
GUN_ADI = ["Pzt", "Sal", "Car", "Per", "Cum", "Cmt", "Paz"]


def _norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = re.sub(r"\s+", " ", s.strip().lower())
    return s


def _yukle():
    try:
        veri = json.loads(DOSYA.read_text(encoding="utf-8"))
        if isinstance(veri, list):
            return veri
    except Exception:
        pass
    return []


def _kaydet(liste):
    DOSYA.parent.mkdir(parents=True, exist_ok=True)
    DOSYA.write_text(json.dumps(liste, ensure_ascii=False, indent=2),
                     encoding="utf-8")


def zaman_cozumle(zaman):
    """Turkce zaman ifadesi -> sema. Cozulemezse (None, ipucu)."""
    z = _norm(zaman)
    if not z:
        return None, "Zaman belirtilmemis. Ornek: 'her sabah 08:00', 'her 30 dakikada'."

    # --- aralik: "her 30 dakikada", "her 10 dk", "her yarim saatte", "her saat", "saat basi"
    m = re.search(r"her\s+(\d+)\s*(dakika|dk| dakika)", z)
    if m:
        dk = max(5, min(int(m.group(1)), 1440))
        return {"tip": "aralik", "dakika": dk}, ""
    if re.search(r"her\s+(yarim|yarım)\s+saatte", z):
        return {"tip": "aralik", "dakika": 30}, ""
    if re.search(r"her\s+(\d+)\s+saatte", z):
        sa = int(re.search(r"her\s+(\d+)\s+saatte", z).group(1))
        return {"tip": "aralik", "dakika": max(5, min(sa * 60, 1440))}, ""
    if re.search(r"her\s+saat\b|saat\s+basi|saat\s+başı", z):
        return {"tip": "aralik", "dakika": 60}, ""

    # --- saat bul: 08:00, 8:00, 08.00, "sabah 8", "aksam 8", "oge 1"
    hh, mm = None, 0
    m = re.search(r"(\d{1,2})[:.](\d{2})", z)
    if m:
        hh, mm = int(m.group(1)) % 24, int(m.group(2)) % 60
    else:
        m2 = re.search(r"(sabah|ogle|öğle|aksam|akşam|gece)\s+(\d{1,2})", z)
        if m2:
            dilim, sa = m2.group(1), int(m2.group(2))
            if dilim.startswith("sabah"):
                hh = sa if sa in (6, 7, 8, 9, 10, 11) else sa % 12 or 8
                if not (0 <= hh <= 11):
                    hh = hh % 12
            elif dilim in ("ogle", "öğle"):
                hh = 12 if sa in (12, 1, 2) else sa
            elif dilim.startswith("aksam") or dilim.startswith("akşam"):
                hh = sa + 12 if sa < 12 else sa
            else:  # gece
                hh = sa if sa <= 5 or sa == 24 else (sa % 12)
                if hh == 24:
                    hh = 0
            hh %= 24
        else:
            # yalın saat: "hafta ici 9", "her pazartesi 10" -> 09:00 / 10:00
            m3 = re.search(r"(\d{1,2})\s*$", z)
            if m3 and int(m3.group(1)) <= 23:
                hh = int(m3.group(1)) % 24
    if hh is None:
        return None, ("Saati anlayamadim: '" + str(zaman)[:60] + "'. "
                      "Ornek: 'her sabah 08:00', 'her aksam 20:30', 'her 30 dakikada'.")

    # --- gun filtresi
    gunler = None
    if re.search(r"hafta\s+i[cç]i", z):
        gunler = [0, 1, 2, 3, 4]
    else:
        for ad, no in GUNLER.items():
            if ad in z:
                gunler = [no]
                break
    if gunler is not None and len(gunler) == 1:
        tip = "haftalik"
    else:
        tip = "gunluk"
    return {"tip": tip, "saat": "%02d:%02d" % (hh, mm),
            "gunler": gunler}, ""


def _sonraki_hesapla(sema, simdi=None):
    simdi = simdi or datetime.now()
    if sema["tip"] == "aralik":
        return simdi + timedelta(minutes=int(sema["dakika"]))
    hh, mm = int(sema["saat"][:2]), int(sema["saat"][3:5])
    aday = simdi.replace(hour=hh, minute=mm, second=0, microsecond=0)
    gunler = sema.get("gunler")
    for _ in range(8):
        if aday > simdi and (not gunler or aday.weekday() in gunler):
            return aday
        aday += timedelta(days=1)
        aday = aday.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return aday


def _sema_ozet(sema):
    if sema["tip"] == "aralik":
        dk = int(sema["dakika"])
        if dk % 60 == 0:
            return "her %d saatte" % (dk // 60)
        return "her %d dakikada" % dk
    gunler = sema.get("gunler")
    if gunler == [0, 1, 2, 3, 4]:
        return "hafta ici " + sema["saat"]
    if gunler and len(gunler) == 1:
        ad = [k for k, v in GUNLER.items() if v == gunler[0] and len(k) > 5]
        return "her " + (ad[0] if ad else "?") + " " + sema["saat"]
    return "her gun " + sema["saat"]


def gorev_kur(talimat, zaman):
    t = str(talimat or "").strip()
    if not t:
        return "Talimat bos. Ne yapmam gerektigini soyle."
    sema, hata = zaman_cozumle(zaman)
    if sema is None:
        return hata
    liste = _yukle()
    yeni_id = 1
    for g in liste:
        try:
            yeni_id = max(yeni_id, int(g.get("id", 0)) + 1)
        except Exception:
            pass
    sonraki = _sonraki_hesapla(sema)
    liste.append({
        "id": yeni_id, "talimat": t, "zaman": str(zaman or "").strip(),
        "sema": sema, "aktif": True,
        "son": "", "sonraki": sonraki.strftime("%Y-%m-%d %H:%M"),
    })
    _kaydet(liste)
    return ("Kuruldu (#" + str(yeni_id) + " - " + _sema_ozet(sema) +
            ", sonraki: " + sonraki.strftime("%d.%m %H:%M") + "): " + t)


def gorev_listele():
    liste = _yukle()
    if not liste:
        return "Kurulu otomatik gorev yok."
    satirlar = []
    for g in liste:
        durum = "ACIK" if g.get("aktif") else "KAPALI"
        satirlar.append("#" + str(g.get("id")) + " [" + durum + "] " +
                        _sema_ozet(g.get("sema", {})) + " - " +
                        str(g.get("talimat", ""))[:90] +
                        " (sonraki: " + str(g.get("sonraki", "?")) + ")")
    return "Otomatik gorevler (" + str(len(satirlar)) + "):\n" + "\n".join(satirlar)


def gorev_sil(hedef):
    h = _norm(hedef)
    if not h:
        return "Hangi gorev silinecek? Numarasini ya da adini soyle."
    liste = _yukle()
    if not liste:
        return "Silinecek gorev yok."
    m = re.search(r"#?(\d+)", h)
    kalan, silinen = [], []
    for g in liste:
        eslesti = False
        if m and int(m.group(1)) == int(g.get("id", -1)):
            eslesti = True
        elif h and h in _norm(g.get("talimat", "")):
            eslesti = True
        if eslesti:
            silinen.append(g)
        else:
            kalan.append(g)
    if not silinen:
        return "Eslesen gorev bulunamadi: " + str(hedef)[:60]
    _kaydet(kalan)
    return ("Silindi (" + str(len(silinen)) + "): " +
            ", ".join("#" + str(g.get("id")) for g in silinen))


def vadesi_gelenler():
    simdi = datetime.now()
    liste = _yukle()
    vade = []
    for g in liste:
        if not g.get("aktif"):
            continue
        try:
            snr = datetime.strptime(str(g.get("sonraki", "")), "%Y-%m-%d %H:%M")
        except Exception:
            snr = simdi
        if snr <= simdi:
            vade.append(g)
    return vade


def calisti_isaretle(gorev_id):
    liste = _yukle()
    simdi = datetime.now()
    for g in liste:
        if int(g.get("id", -1)) == int(gorev_id):
            g["son"] = simdi.strftime("%Y-%m-%d %H:%M")
            try:
                g["sonraki"] = _sonraki_hesapla(g.get("sema", {}),
                                                simdi).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
    _kaydet(liste)


def sonuc_yaz(gorev, ozet):
    try:
        SONUC_DOSYA.parent.mkdir(parents=True, exist_ok=True)
        kayit = {"zaman": time.strftime("%d.%m %H:%M"), "id": gorev.get("id"),
                 "talimat": str(gorev.get("talimat", ""))[:120],
                 "ozet": str(ozet or "")[:1500]}
        with open(SONUC_DOSYA, "a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
        # dosya sismesin: son 200 satir
        try:
            satirlar = SONUC_DOSYA.read_text(encoding="utf-8").splitlines()
            if len(satirlar) > 200:
                SONUC_DOSYA.write_text("\n".join(satirlar[-200:]) + "\n",
                                       encoding="utf-8")
        except Exception:
            pass
    except Exception:
        pass


def gorev_sonuclari(sayi="5"):
    try:
        n = max(1, min(int(sayi), 20))
    except Exception:
        n = 5
    try:
        satirlar = SONUC_DOSYA.read_text(encoding="utf-8").splitlines()
    except Exception:
        return "Henuz calisan otomatik gorev yok."
    if not satirlar:
        return "Henuz calisan otomatik gorev yok."
    cikti = []
    for s in satirlar[-n:]:
        try:
            k = json.loads(s)
            cikti.append(k.get("zaman", "?") + " (#" + str(k.get("id")) +
                         " " + str(k.get("talimat", ""))[:60] + "): " +
                         str(k.get("ozet", ""))[:300])
        except Exception:
            continue
    if not cikti:
        return "Sonuc kaydi okunamadi."
    return "Son gorev sonuclari:\n" + "\n---\n".join(cikti)
