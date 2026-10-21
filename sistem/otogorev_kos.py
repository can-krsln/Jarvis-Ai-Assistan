#!/usr/bin/env python3
"""Otomatik gorev kosucusu — JARVIS kapaliyken bile calisir.

Windows Gorev Zamanlayici'da 5 dakikada bir calistirilir:
  schtasks /Create /TN "JARVIS-OtoGorev" /TR "...pythonw.exe otogorev_kos.py"
    /SC MINUTE /MO 5

Yapar:
  1. vadesi gelen gorevleri bulur (yoksa sessizce cikar),
  2. her birini Gemini (generate_content + araclar) ile calistirir,
  3. sonucu kuyruk/otogorev-sonuc.jsonl'ye yazar, sonraki zamani ilerletir.

Cakisma kilidi: kuyruk/otogorev.lock (15 dakikadan eski kilit devralinir).
"""

from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app_config import get_app_config_value
from tool_defs import TOOL_DECLARATIONS
from actions.otogorev import (
    vadesi_gelenler, calisti_isaretle, sonuc_yaz,
)

KOSUCU_ARACLAR_HARIC = {"gorev_kur", "gorev_sil"}
MODEL = "models/gemini-2.5-flash"
EN_FAZLA_TUR = 10
KILIT = BASE_DIR / "kuyruk" / "otogorev.lock"


def _kilit_al():
    try:
        KILIT.parent.mkdir(parents=True, exist_ok=True)
        if KILIT.exists():
            try:
                yas = time.time() - KILIT.stat().st_mtime
                if yas < 15 * 60:
                    return False
            except Exception:
                return False
        KILIT.write_text(str(datetime.now()), encoding="utf-8")
        return True
    except Exception:
        return False


def _kilit_birak():
    try:
        if KILIT.exists():
            KILIT.unlink()
    except Exception:
        pass


def _arac_calistir(ad, argumanlar):
    from jarvis_web.agent import execute_tool
    try:
        return str(execute_tool(ad, dict(argumanlar or {})) or "Tamam.")
    except Exception as e:
        return "Hata: " + str(e)[:300]


def _gorevi_calistir(gorev):
    api_key = str(get_app_config_value("gemini_api_key", "") or "").strip()
    if not api_key:
        return "API anahtari yok, calistirilamadi."
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        return "Model kutuphanesi yok: " + str(e)[:150]

    bildiriler = [d for d in TOOL_DECLARATIONS
                  if d.get("name") not in KOSUCU_ARACLAR_HARIC]
    cfg = types.GenerateContentConfig(
        tools=[{"function_declarations": bildiriler}],
        temperature=0.4,
        system_instruction=(
            "Sen JARVIS'in otomatik gorev kosucususun. Kullanicinin onceden "
            "kurmus oldugu su gorevi yerine getir. Gerekli araclari kullan, "
            "kisa ve net Turkce ile SONUCU ozetle. Soru sorma, kullanici yok; "
            "yapabildigini yap, yapamadigini ozette soyle."
        ),
    )
    istem = ("[OTOMATIK GOREV - " +
             datetime.now().strftime("%d.%m %H:%M") + "]\n" +
             str(gorev.get("talimat", "")))
    try:
        istemci = genai.Client(api_key=api_key)
        icerik = [types.Content(role="user",
                                parts=[types.Part.from_text(text=istem)])]
        ozet = ""
        for _ in range(EN_FAZLA_TUR):
            cevap = istemci.models.generate_content(
                model=MODEL, contents=icerik, config=cfg)
            try:
                aday = cevap.candidates[0]
            except Exception:
                ozet = "Model cevap vermedi."
                break
            icerik.append(aday.content)
            cagrilar = [p.function_call for p in (aday.content.parts or [])
                        if getattr(p, "function_call", None)]
            if not cagrilar:
                try:
                    ozet = (cevap.text or "").strip() or "Sonuc metni yok."
                except Exception:
                    ozet = "Tamamlandi."
                break
            yanit_parcalari = []
            for fc in cagrilar:
                sonuc = _arac_calistir(fc.name, fc.args)
                yanit_parcalari.append(
                    types.Part.from_function_response(
                        name=fc.name, response={"result": sonuc}))
            icerik.append(types.Content(role="function",
                                        parts=yanit_parcalari))
        else:
            ozet = "Cok adimli gorev sinira takildi, yari birakildi."
        return ozet[:1500] if ozet else "Tamamlandi."
    except Exception as e:
        return "Kosucu hatasi: " + str(e)[:300]


def main():
    if not _kilit_al():
        return 0
    try:
        vade = vadesi_gelenler()
        for gorev in vade:
            try:
                ozet = _gorevi_calistir(gorev)
            except Exception:
                traceback.print_exc()
                ozet = "Beklenmeyen hata."
            sonuc_yaz(gorev, ozet)
            calisti_isaretle(gorev.get("id"))
        return 0
    finally:
        _kilit_birak()


if __name__ == "__main__":
    raise SystemExit(main())
