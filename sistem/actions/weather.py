"""
Hava durumu ozeti — wttr.in uzerinden.

Konum onceligi:
1. Cagriya verilen `location` (kullanici "Ankara'da hava nasil" dediyse)
2. config/api_keys.json → "weather_location"  (elle sabitlemek isteyen icin)
3. JARVIS_WEATHER_LOCATION ortam degiskeni
4. OTOMATIK: wttr.in istegi IP'den konumu kendisi bulur

Eskiden herkes icin "Istanbul" sabitti; artik kullanicinin bulundugu sehir
otomatik tespit ediliyor ve tespit edilen sehir adi onbellege aliniyor.
"""

from __future__ import annotations

import os
import threading

import requests

from actions.platform_utils import PLATFORM_LABEL

try:
    from app_config import get_app_config_value
except Exception:  # app_config yoksa (tek basina kullanim)
    def get_app_config_value(key, default=None):
        return default


_detected_city = ""          # otomatik bulunan sehir (onbellek)
_lock = threading.Lock()

REQUEST_TIMEOUT = 12
HEADERS = {"User-Agent": f"JARVIS {PLATFORM_LABEL}"}


def configured_location() -> str:
    """Kullanicinin elle sabitledigi konum (yoksa bos)."""
    value = str(get_app_config_value("weather_location", "") or "").strip()
    if value:
        return value
    return (os.environ.get("JARVIS_WEATHER_LOCATION") or "").strip()


def detected_city() -> str:
    """Otomatik tespit edilen sehir; henuz sorgulanmadiysa bos doner."""
    with _lock:
        return _detected_city


def current_location_label() -> str:
    """Arayuzde gosterilecek konum adi."""
    return configured_location() or detected_city() or "Konum araniyor"


def _extract_city(payload: dict) -> str:
    """
    Sehir adini cikarir.

    wttr.in'in 'areaName' alani cok yerel olabiliyor (Istanbul yerine
    "Kucukpazar", Ankara yerine "Samanpazari"). Kullaniciya sehir adi daha
    anlamli oldugu icin once 'region' tercih edilir.
    """
    try:
        area = (payload.get("nearest_area") or [{}])[0]
        name = ((area.get("areaName") or [{}])[0]).get("value", "").strip()
        region = ((area.get("region") or [{}])[0]).get("value", "").strip()
        return region or name
    except Exception:
        return ""


def get_weather_summary(location: str | None = None) -> str:
    explicit = (location or "").strip()
    target = explicit or configured_location()

    # target bossa wttr.in'e sehir vermeden sorariz; kendisi IP'den bulur
    url = f"https://wttr.in/{target}" if target else "https://wttr.in"

    try:
        response = requests.get(
            url, params={"format": "j1"},
            timeout=REQUEST_TIMEOUT, headers=HEADERS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        known = target or detected_city()
        if known:
            return f"{known} icin hava durumu bilgisi su anda alinamadi."
        return "Hava durumu bilgisi şu anda alınamadı."

    detected = _extract_city(payload)
    if not target and detected:
        # Otomatik bulunan sehri hatirla (arayuz kartinda da kullanilir)
        with _lock:
            global _detected_city
            _detected_city = detected

    # Kullanici acikca bir yer soylediyse ONUN kelimesini kullan:
    # "Ankara" isteyip "Samanpazari" duymak kafa karistirici.
    city = target or detected

    current = (payload.get("current_condition") or [{}])[0]
    temp_c = current.get("temp_C")
    feels_like = current.get("FeelsLikeC")
    weather_desc = ((current.get("weatherDesc") or [{}])[0]).get("value", "")
    humidity = current.get("humidity")

    parts = []
    if temp_c:
        parts.append(f"{temp_c} derece")
    if weather_desc:
        parts.append(weather_desc.lower())
    if feels_like and feels_like != temp_c:
        parts.append(f"hissedilen {feels_like} derece")
    if humidity:
        parts.append(f"nem yüzde {humidity}")

    if not parts:
        return "Hava durumu bilgisi şu anda alınamadı."

    label = city or "Bulunduğun konum"
    return f"{label} için hava durumu: " + ", ".join(parts) + "."
