# J.A.R.V.I.S

Gerçek zamanlı sesli kişisel asistan. Google **Gemini Live API** ile konuşur,
bilgisayarını sesle kontrol eder. **macOS ve Windows**'ta tek kod tabanıyla çalışır.

Türkçe konuşur, Türkçe anlar.

---

## Ne yapabiliyor

| | |
|---|---|
| 🎙️ **Sesli sohbet** | Gemini Live ile kesintisiz konuşma (sözünü kesebilirsin) |
| 📅 **Takvim** | Etkinlik ekle/oku/sil — Outlook veya JARVIS'in kendi takvimi |
| ⏰ **Anımsatıcılar** | Zamanlı hatırlatmalar |
| 💬 **WhatsApp** | Kişi adı veya numarayla mesaj hazırla / gönder |
| 🖥️ **Ekran analizi** | Aktif pencereyi Gemini vision ile okur, hataları söyler |
| 📷 **Kamera** | Webcam görüntüsünü modele canlı aktarır |
| 🎵 **Medya** | Spotify veya YouTube'da müzik çalar |
| 🚀 **Uygulama açma** | "hesap makinesini aç" — Başlat menüsünü tarar |
| 💻 **Kabuk** | PowerShell (Windows) / bash (macOS) komutları, güvenlik filtreli |
| 🌤️ **Hava durumu**, 📊 **sistem bilgisi**, 🧠 **kalıcı hafıza** | |
| 📱 **Telefondan kontrol** | Telefon tarayıcısından kendi bilgisayarını kullan |

---

## Kurulum

### Windows

**En kolay yol — EXE:** `JARVIS-Windows-EXE` paketini indir, `JARVIS.exe`'ye çift tıkla.
Python kurmana gerek yok.

**Kaynaktan:**

```
BASLAT.bat
```

Çift tıkla, gerisini kendisi halleder — Python 3.12'yi kurar (winget), sanal ortam
oluşturur, paketleri yükler, masaüstü kısayolu ekler ve başlatır.

### macOS

```
BASLAT.command
```

---

İlk açılışta **Gemini API anahtarı** ister (ücretsiz):
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) → "Create API key"

---

## Gereksinimler

- **Python 3.11+** — `asyncio.TaskGroup` kullanılıyor (EXE sürümde gerekmez)
- Mikrofon
- İnternet bağlantısı

Bağımlılıklar `requirements.txt` içinde; Windows'a özel olanlar (`pywin32`, `mss`,
`pyttsx3`, `pywinauto`) platform işaretiyle ayrılmıştır.

---

## Kendi EXE'ni derlemek

```
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

Çıktı: `dist\JARVIS\JARVIS.exe` (yanındaki `_internal` klasörüyle birlikte taşınır).

| Seçenek | Etkisi |
|---|---|
| `-Console` | Konsol penceresiyle derler (hata ayıklama) |
| `-OneFile` | Tek dosya .exe — her açılışta paketi açtığı için ~10 sn daha yavaş |
| `-Clean` | Sıfırdan derler |

Sorun tanısı için: `JARVIS.exe --selftest` → yollar, moduller ve araçlar test edilir,
yanına `jarvis_tani.log` yazar.

---

## Paylaşım paketi hazırlamak

```
powershell -ExecutionPolicy Bypass -File hazirla_paylasim.ps1 -Mode hepsi -Zip
```

Kişisel veriler (API anahtarı, kişiler, takvim, hafıza) **hiçbir pakete dahil edilmez**.

---

## Proje yapısı

```
main.py              Gemini Live çekirdeği, ses döngüsü, araç dağıtımı
ui.py                tkinter arayüz (animasyonlu orb, paneller)
tool_defs.py         Gemini araç (function-calling) tanımları
app_paths.py         kaynak (salt-okunur) / veri (yazılabilir) yol ayrımı
prompt_loader.py     sistem promptunu platforma uyarlar
actions/
  platform_utils.py  IS_WIN / IS_MAC, PowerShell, COM, konsol koruması
  win_organizer.py   Windows takvim + anımsatıcı (Outlook COM veya yerel depo)
  audio_player.py    SFX — macOS afplay / Windows MCI
  calendar.py  reminders.py  whatsapp.py  media.py  screen_vision.py
  shell.py  open_app.py  browser.py  sys_info.py  tts.py  weather.py
core/prompt.txt      sistem promptu (tek dosya, Windows'a otomatik uyarlanır)
jarvis_web/          telefon → PC sunucusu + ajan
```

**Platform dallanması:** ayrı bir Windows kopyası yok. Platforma özel her yer
`actions/platform_utils.py` içindeki `IS_WIN` / `IS_MAC` ile ayrılır.

---

## Yapılandırma

`config/api_keys.json`:

| Anahtar | Açıklama |
|---|---|
| `gemini_api_key` | Zorunlu |
| `voice` | Gemini sesi (Charon, Puck, Aoede, Kore, Fenrir, Leda, Orus, Zephyr) |
| `calendar_backend` | `auto` (varsayılan) / `outlook` / `local` |

**`calendar_backend` neden var:** Outlook COM, yapılandırılmamış bir Outlook'ta
kurulum sihirbazını açıp uygulamayı kilitleyebiliyor. `auto` modunda JARVIS
yalnızca *zaten açık* bir Outlook'a bağlanır, aksi halde kendi yerel takvimini
kullanır — her makinede kurulumsuz çalışır.

---

## Gizlilik

- Ses ve ekran görüntüleri yalnızca **senin** Gemini API anahtarınla Google'a gider.
- API anahtarı, hafıza, rehber ve takvim sadece **senin bilgisayarında** durur.
- Telefon sunucusunun adresi/token'ı bir **şifre gibidir** — bilgisayarına tam
  erişim verir, paylaşma.

---

## Telefondan kontrol

`TELEFON.bat` (EXE pakette de var) sunucuyu, bilgisayar ajanını ve — açıksa —
Cloudflare tünelini başlatır; ekrana adres + QR kod basar.

EXE sürümünde `python server.py` çalıştırılamayacağı için `JARVIS.exe` kendini
farklı bayraklarla yeniden çağırır:

| Komut | İş |
|---|---|
| `JARVIS.exe --web` | orkestratör: sunucu + ajan + (opsiyonel) tünel, QR basar |
| `JARVIS.exe --web-server` | yalnızca sunucu süreci |
| `JARVIS.exe --web-agent` | yalnızca bilgisayar ajanı |

Süreçler ayrı kalır — biri çökerse diğeri ayakta kalır, mimari kaynak
sürümüyle aynıdır.

**İnternet üzerinden erişim varsayılan AÇIKTIR** — telefon her yerden
bağlanır ve adres gerçek sertifikalı olduğu için tarayıcı uyarısı çıkmaz.
Sunucu yalnızca kullanıcı "JARVIS TELEFON"u başlattığında çalışır ve adres
token ile korunur. Sadece yerel ağla sınırlamak için
`config/api_keys.json` içine `"web_remote_access": false` — o durumda
kendinden imzalı sertifika yüzünden tarayıcı uyarı verir.

Tünel için `cloudflared` (Apache-2.0, Cloudflare Inc. imzalı) EXE paketine
dahildir; kaynak sürümde `build_exe.ps1` gerektiğinde indirir. Ücretsiz
TryCloudflare tünelinin adresi her başlatmada değişir.

## Bilinen sınırlar

- Ücretsiz Cloudflare tüneli "test/geliştirme için" olarak sunulur: adres her
  açılışta değişir, aynı anda 200 istek sınırı vardır, SLA yoktur.
- Outlook'a *yazma* yolu yapılandırılmış bir profil gerektirir.
- `core/prompt.txt` içindeki `get_health_data` örnekleri macOS'a özeldir; bu araç
  `tool_defs.py`'de tanımlı değildir.
- Spotify/WhatsApp otomasyonu tuş simülasyonu kullanır — o sırada başka pencereye
  tıklarsan tuşlar oraya gidebilir.
