"""OTO-YETENEK: JARVIS'in kendini genisletme motoru.

Doktrin: kullanici bir is ister ve hazir arac yoksa ASLA "yapamam / yok /
desteklenmiyor" denmez. Model `yetenek_ekle` ile eksik yetenegi kendisi kodlar,
kutuphaneye kaydeder, `yetenek_calistir` ile calistirir.

Depo:
  sistem/actions/oto_kutuphane/<ad>.py   (uretilen yetenek modulleri)
  sistem/memory/yetenekler.json          (kayit defteri)

Surum-notu: eklenen yetenek ayni oturumda yetenek_calistir ile hemen,
sonraki oturumlarda dogrudan adiyla cagrilabilir (TOOL_DECLARATIONS'a
best-effort eklenir + restart sonrasi kalici).
"""

from __future__ import annotations

import importlib.util
import json
import keyword
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent          # sistem/actions
KUTUPHANE = BASE_DIR / "oto_kutuphane"
KAYIT_DOSYA = BASE_DIR.parent / "memory" / "yetenekler.json"

AD_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
SONUC_LIMIT = 4000


def _kayit_oku() -> dict:
    try:
        return json.loads(KAYIT_DOSYA.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _kayit_yaz(kayit: dict) -> None:
    KAYIT_DOSYA.parent.mkdir(parents=True, exist_ok=True)
    KAYIT_DOSYA.write_text(json.dumps(kayit, ensure_ascii=False, indent=1),
                           encoding="utf-8")


def _mevcut_adlar() -> set:
    """Uzerine yazilmamasi gereken adlar: mevcut aksiyon fonksiyonlari +
    mevcut arac isimleri + kayitli yetenekler."""
    adlar: set = set()
    try:
        for f in BASE_DIR.glob("*.py"):
            try:
                txt = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for m in re.finditer(r"^def (\w+)", txt, re.M):
                adlar.add(m.group(1))
    except Exception:
        pass
    try:
        from tool_defs import TOOL_DECLARATIONS
        for d in TOOL_DECLARATIONS:
            n = (d or {}).get("name")
            if n:
                adlar.add(n)
    except Exception:
        pass
    try:
        adlar.update(_kayit_oku().keys())
    except Exception:
        pass
    return adlar


def yetenek_ekle(ad: str, aciklama: str, kod: str, parametreler=None) -> str:
    """Eksik yetenegi kodlayip kutuphaneye ekler.

    ad: kucuk harf/snake_case, orn: 'pdf_oku'
    aciklama: modelin ne zaman kullanacagini anlatan 1-2 cumle
    kod: 'def calistir(...)' iceren Python kodu (return degeri str olmali)
    parametreler: {param_adi: aciklama} dict'i ya da JSON stringi
    """
    ad = (ad or "").strip().lower()
    if not AD_RE.match(ad):
        return ("Hata: yetenek adi '%s' gecersiz. kucuk harf, rakam ve _ "
                "kullan, 3-40 karakter." % ad)
    if keyword.iskeyword(ad):
        return "Hata: '%s' Python anahtar kelimesi, baska ad sec." % ad
    if ad in _mevcut_adlar():
        return ("Hata: '%s' adi zaten kullaniliyor (mevcut arac ya da "
                "yetenek). Yeni bir ad sec ya da yetenek_listele ile bak."
                % ad)
    if "def calistir" not in (kod or ""):
        return ("Hata: kod 'def calistir(...)' fonksiyonu icermeli. "
                "Sonucu return ile str olarak dondur.")
    if isinstance(parametreler, str):
        try:
            parametreler = json.loads(parametreler) if parametreler.strip() else {}
        except Exception:
            return "Hata: parametreler JSON anlasilmadi."
    parametreler = parametreler or {}
    try:
        KUTUPHANE.mkdir(parents=True, exist_ok=True)
        hedef = KUTUPHANE / (ad + ".py")
        baslik = ("# %s - oto-yetenek (JARVIS uretti)\n# %s\n\n"
                  % (ad, (aciklama or "").strip().replace("\n", " ")))
        hedef.write_text(baslik + kod + "\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location("oto_" + ad, str(hedef))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not callable(getattr(mod, "calistir", None)):
            hedef.unlink(missing_ok=True)
            return "Hata: modül yüklendi ama calistir() bulunamadi."
    except Exception as e:
        try:
            (KUTUPHANE / (ad + ".py")).unlink(missing_ok=True)
        except Exception:
            pass
        return "Hata: yetenek kodu calismadi: %s" % str(e)[:300]

    kayit = _kayit_oku()
    kayit[ad] = {"aciklama": (aciklama or "").strip(),
                 "parametreler": parametreler}
    _kayit_yaz(kayit)
    # Ayni surecte calisan oturuma da tanit (restart sonrasi zaten kalici)
    try:
        from tool_defs import TOOL_DECLARATIONS
        props = {k: {"type": "STRING", "description": str(v)}
                 for k, v in parametreler.items()}
        TOOL_DECLARATIONS.append({
            "name": ad,
            "description": (aciklama or ad) + " (oto-yetenek)",
            "parameters": {"type": "OBJECT", "properties": props,
                           "required": list(props.keys())},
        })
    except Exception:
        pass
    return ("'%s' eklendi ve kaydedildi. Bu oturumda yetenek_calistir ile "
            "hemen kullan; sonraki oturumlarda dogrudan adiyla cagrilir."
            % ad)


def yetenek_calistir(ad: str, argumanlar=None) -> str:
    """Kayitli yetenegi calistirir. argumanlar: dict ya da JSON string."""
    ad = (ad or "").strip().lower()
    kayit = _kayit_oku()
    if ad not in kayit:
        return ("Hata: '%s' kayitli degil. yetenek_listele ile mevcutlara "
                "bak ya da yetenek_ekle ile olustur." % ad)
    if isinstance(argumanlar, str):
        try:
            argumanlar = json.loads(argumanlar) if argumanlar.strip() else {}
        except Exception:
            return "Hata: argumanlar JSON anlasilmadi."
    argumanlar = argumanlar or {}
    try:
        hedef = KUTUPHANE / (ad + ".py")
        spec = importlib.util.spec_from_file_location("oto_" + ad, str(hedef))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sonuc = mod.calistir(**argumanlar)
        return str(sonuc)[:SONUC_LIMIT] or "Tamam."
    except TypeError as e:
        return ("Hata: parametre uyusmazligi (%s). Kayitli parametreler: %s"
                % (str(e)[:200], json.dumps(kayit[ad].get("parametreler", {}),
                                            ensure_ascii=False)))
    except Exception as e:
        return "Hata: '%s' calisirken: %s" % (ad, str(e)[:300])


def yetenek_listele() -> str:
    """Kutuphanedeki tum yetenekleri listeler."""
    kayit = _kayit_oku()
    if not kayit:
        return ("Kutuphane henuz bos. Eksik bir yetenek lazim oldugunda "
                "yetenek_ekle ile olustur.")
    satirlar = []
    for ad in sorted(kayit):
        b = kayit[ad]
        params = ", ".join((b.get("parametreler") or {}).keys()) or "parametresiz"
        satirlar.append("- %s: %s [%s]" % (ad, b.get("aciklama", ""), params))
    return "\n".join(satirlar)


def yetenek_sil(ad: str) -> str:
    """Yetenegi kutuphaneden kaldirir (dosya + kayit)."""
    ad = (ad or "").strip().lower()
    kayit = _kayit_oku()
    if ad not in kayit:
        return "Hata: '%s' kayitli degil." % ad
    try:
        (KUTUPHANE / (ad + ".py")).unlink(missing_ok=True)
    except Exception:
        pass
    kayit.pop(ad, None)
    _kayit_yaz(kayit)
    try:
        from tool_defs import TOOL_DECLARATIONS
        TOOL_DECLARATIONS[:] = [d for d in TOOL_DECLARATIONS
                                if (d or {}).get("name") != ad]
    except Exception:
        pass
    return "'%s' silindi." % ad


def oto_dispatch(name: str, args: dict) -> str:
    """main.py bilinmeyen-arac dususu: dinamik kutuphane + kilavuz.

    DİKKAT: basari/kilavuz mesajlari hata-isaretcisi kelimelerle
    baslamamali (bkz: _result_looks_like_error), yoksa UI ERROR'a duser.
    """
    args = args or {}
    if name == "yetenek_ekle":
        return yetenek_ekle(args.get("ad", ""), args.get("aciklama", ""),
                            args.get("kod", ""), args.get("parametreler", {}))
    if name == "yetenek_calistir":
        return yetenek_calistir(args.get("ad", ""), args.get("argumanlar", {}))
    if name == "yetenek_listele":
        return yetenek_listele()
    if name == "yetenek_sil":
        return yetenek_sil(args.get("ad", ""))
    kayit = _kayit_oku()
    if name in kayit:
        return yetenek_calistir(name, args)
    return ("'%s' adinda hazir arac yok. Cozum sende: bu isi yapan kisa bir "
            "Python cozumu yaz (shell_run, dosya_oku, dosya_yaz, "
            "browser_control, program_kur elinin altinda), yetenek_ekle ile "
            "kutuphaneye kaydet, sonra yetenek_calistir ile calistir. "
            "Kullaniciya 'yok' demeden once mutlaka bu yolu dene." % name)

def kayitli_yetenek_bildirimleri() -> list:
    """Restart sonrasi kayitli yetenekleri arac listesine tasir.

    tool_defs.py acilista cagirir; boylece kutuphanedeki her yetenek
    model icin birinci sinif arac olur (yetenek_listele'ye bakmaya gerek kalmaz).
    """
    decls = []
    try:
        kayit = _kayit_oku()
    except Exception:
        return []
    for ad, b in kayit.items():
        try:
            if not AD_RE.match(ad or ""):
                continue
            b = b or {}
            params = b.get("parametreler") or {}
            props = {k: {"type": "STRING", "description": str(v)}
                     for k, v in params.items()}
            decls.append({
                "name": ad,
                "description": "%s (oto-yetenek)" % (b.get("aciklama") or ad),
                "parameters": {"type": "OBJECT", "properties": props,
                               "required": list(props.keys())},
            })
        except Exception:
            continue
    return decls
