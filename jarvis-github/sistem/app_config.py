from __future__ import annotations

import json
from pathlib import Path


from app_paths import data_path

# Kullanici anahtarlarini yazar → veri koku (exe'de paketin ici degil)
CONFIG_PATH = data_path("config", "api_keys.json")
CONFIG_DIR = CONFIG_PATH.parent
BASE_DIR = CONFIG_DIR.parent


DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "voice": "Charon",
    # Windows takvim/animsatici arka ucu:
    #   "auto"    → Outlook zaten aciksa onu, degilse JARVIS yerel takvimini kullan
    #   "outlook" → Outlook'u zorla (gerekirse baslatir)
    #   "local"   → her zaman JARVIS yerel takvimi
    "calendar_backend": "auto",
    # Telefondan INTERNET uzerinden erisim (cloudflared tuneli).
    # VARSAYILAN ACIK. Sebep: kapaliyken telefon yalnizca ayni Wi-Fi'dan
    # baglanabiliyor ve kendinden imzali sertifika yuzunden tarayici
    # "bu baglanti ozel degil" uyarisi veriyor; ayrica IP degisince adres
    # gecersiz oluyor. Tunel ile gercek sertifikali, her yerden calisan bir
    # adres uretiliyor. Sunucu YALNIZCA kullanici "JARVIS TELEFON"u
    # baslattiginda calisir; adres token ile korunur.
    # Kapatmak icin: false yap → yalnizca ayni Wi-Fi agindan erisilir.
    "web_remote_access": True,
    # Hava durumu konumu. Bos birakilirsa bulundugun sehir otomatik bulunur.
    "weather_location": "",
}


def load_app_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            config.update(raw)
    except Exception:
        pass
    return config


def save_app_config(updates: dict) -> dict:
    config = load_app_config()
    for key, value in (updates or {}).items():
        if value is None:
            continue
        config[key] = value
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )
    return config


def get_app_config_value(key: str, default=None):
    return load_app_config().get(key, default)


def has_gemini_api_key() -> bool:
    value = str(get_app_config_value("gemini_api_key", "") or "").strip()
    return bool(value)
