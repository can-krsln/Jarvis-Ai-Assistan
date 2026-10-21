# J.A.R.V.I.S Web

Telefon ve bilgisayar tarayıcısından çalışan JARVIS. Mac açıkken sistem
araçları (uygulama açma, takvim, shell...) Mac üzerinden yürütülür;
Mac kapalıyken konuşma, hava durumu, bellek ve tarayıcı kamerası çalışmaya
devam eder.

## Mimari

```
[Telefon tarayıcı]   [Bilgisayar tarayıcı]
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │  server.py (FastAPI) │ ← Gemini Live burada koşar
        └──────────┬──────────┘
                   │ websocket (Mac açıkken)
                   ▼
        ┌─────────────────────┐
        │  agent.py (Mac ajanı)│ ← takvim, shell, uygulama açma...
        └─────────────────────┘
```

## Kurulum

```bash
cd jarvis_web
pip3 install -r requirements.txt
```

Gemini API anahtarı ana projedeki `config/api_keys.json`'dan okunur
(masaüstü JARVIS ile aynı). Sunucu başka makinedeyse `GEMINI_API_KEY`
ortam değişkeni de kullanılabilir.

## Çalıştırma — en kolay yol (tek tık)

`jarvis_web/` klasöründeki **WEB_BASLAT.command** dosyasına çift tıkla.
Tek başına şunları yapar:

- Web bağımlılıklarını (fastapi/uvicorn/websockets) kurar
- cloudflared (tünel) ve qrencode'u kurar (yoksa)
- Sunucu + Mac ajanı + Cloudflare tünelini başlatır
- Telefon için **token gömülü tam adresi ve QR kodunu** ekrana basar

Telefonun kamerasıyla QR'ı okut → **otomatik bağlanır** (token elle girme yok).
Pencereyi kapatma; kapatınca web durur. Durdurmak için Ctrl+C.

Gemini API anahtarı ana projedeki `config/api_keys.json`'dan okunur
(masaüstü JARVIS ile aynı — bir kez oradan girmen yeterli).

### Elle çalıştırma (isteğe bağlı)

```bash
python3 server.py     # sunucu (8765 http + 8766 https)
python3 agent.py      # Mac ajanı (sistem araçları)
cloudflared tunnel --url http://localhost:8765   # telefon için genel adres
```

Token URL'e `?t=<token>` olarak eklenirse tarayıcı otomatik bağlanır,
yoksa ilk girişte bir kez sorar (sonra tarayıcıda saklanır).

## ⚠️ Güvenlik

Adres + token, Mac'ine **tam erişim** verir (uygulama açma, shell dahil).
Bir şifre gibi davran: videoda gösterme, kimseyle paylaşma. Sıfırlamak için
`web_config.json`'ı sil ve tekrar başlat — yeni token üretilir.

## Kullanım

| Buton | İşlev |
|-------|-------|
| 🎙️ MIC | Mikrofonu aç/kapat — gerçek zamanlı konuşma |
| 📷 CAM | Tarayıcı kamerasını aç — JARVIS görür (1.5s/kare) |
| Yazı kutusu | Sesli konuşmadan yazılı komut gönder |

Üstteki rozetler: **SUNUCU** = backend bağlantısı, **MAC** = ajan bağlı mı.
MAC rozeti sönükken sistem araçları "bilgisayar bağlı değil" yanıtı verir.

## Güvenlik notları

- Token olmadan hiçbir websocket bağlantısı kabul edilmez.
- İnternete açmadan önce: gerçek bir TLS sertifikası (Let's Encrypt) ve
  güçlü token kullan; `shell_run` aracının tam yetkili olduğunu unutma.
- En güvenli kurulum: sunucu yalnızca yerel ağda, dışarıdan erişim için
  Tailscale/WireGuard VPN.
