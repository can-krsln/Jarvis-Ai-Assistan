"""
Telefon sunucusu — hem konsoldan hem arayuzden calistirilabilir.

Donmus (.exe) uygulamada "python server.py" calistirilamaz. Bunun yerine
JARVIS.exe kendini farkli bayraklarla yeniden cagirir:

    JARVIS.exe --web          → konsol orkestratoru (sunucu + ajan + tunel)
    JARVIS.exe --web-server   → yalnizca sunucu sureci
    JARVIS.exe --web-agent    → yalnizca bilgisayar ajani

Arayuzdeki "JARVIS TELEFON" paneli ise PhoneServer sinifini kullanir:
surecleri arka planda baslatir, adres/token uretir, istenince durdurur.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from app_paths import IS_FROZEN, data_path, resource_path
from app_config import get_app_config_value
from actions.platform_utils import run_quiet


SERVER_PORT = 8765
HTTPS_PORT = 8766
TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _kill_tree(proc) -> None:
    """Sureci COCUKLARIYLA BIRLIKTE oldur.

    Windows'ta .venv\\Scripts\\python.exe bir ara baslaticidir: asil isi
    yapan yorumlayiciyi COCUK surec olarak calistirir. Donmus .exe'de de
    PyInstaller onefile ayni sekilde davranir. Sadece proc.terminate()
    cagirmak ust sureci oldurur, sunucu ve cloudflared tuneli AYAKTA KALIR
    — kullanici "durdurdum" sanirken uzaktan erisim acik kalmis olur.
    Bu yuzden agaci taskkill /T ile komple kapatiyoruz.
    """
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception:
        return
    if os.name == "nt":
        try:
            run_quiet(["taskkill", "/PID", str(proc.pid), "/T", "/F"], timeout=10)
            return
        except Exception:
            pass
    try:
        proc.terminate()
    except Exception:
        pass


# ── Kendini yeniden cagirma ─────────────────────────────────────────────────
def _self_command(flag: str) -> list[str]:
    if IS_FROZEN:
        return [sys.executable, flag]
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return [sys.executable, str(main_py), flag]


def _log_dir() -> Path:
    path = Path(os.environ.get("TEMP", ".")) / "jarvis_web_logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _spawn(flag: str, log_path: Path, extra_env: "dict | None" = None) -> subprocess.Popen:
    handle = open(log_path, "w", encoding="utf-8", errors="replace")
    # Cikti dosyaya yonlendirildiginde Python tamponlar; gunlukler bos
    # gorunuyordu. Tamponlamayi kapat ki sorun aninda gunluge dussun.
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if extra_env:
        env.update(extra_env)
    kwargs = {"stdout": handle, "stderr": subprocess.STDOUT, "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000      # CREATE_NO_WINDOW
    return subprocess.Popen(_self_command(flag), **kwargs)


# ── cloudflared ─────────────────────────────────────────────────────────────
def find_cloudflared() -> "str | None":
    """Once uygulamanin yanindaki kopya, sonra sistemde kurulu olan."""
    candidates = []
    if IS_FROZEN:
        candidates.append(Path(sys.executable).resolve().parent / "cloudflared.exe")
    candidates.append(resource_path("cloudflared.exe"))
    candidates.append(Path(__file__).resolve().parent.parent / "cloudflared.exe")

    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except Exception:
            continue

    from shutil import which

    found = which("cloudflared")
    if found:
        return found
    # Kaynak surumde cloudflared paketle GELMEZ (51 MB). Yoksa indirilmis
    # kopyayi kullan.
    downloaded = data_path("cloudflared.exe")
    try:
        if downloaded.is_file():
            return str(downloaded)
    except Exception:
        pass
    return None


CLOUDFLARED_URL = ("https://github.com/cloudflare/cloudflared/releases/"
                   "latest/download/cloudflared-windows-amd64.exe")


def ensure_cloudflared(on_progress=None) -> "str | None":
    """cloudflared'i bul; yoksa resmi surumu indir.

    NEDEN GEREKLI: cloudflared olmadan tunel kurulamaz ve telefon
    https://<lan-ip>:8766 adresine, yani KENDINDEN IMZALI sertifikaya
    duser. Tarayici sayfa icin verilen sertifika istisnasini WebSocket
    el sikismasina TASIMAZ: sayfa acilir ama baglanti kurulamaz ve
    kullanici "BAGLANTI KOPTU" gorur. Bu yuzden tuneli garantiye aliyoruz.
    """
    existing = find_cloudflared()
    if existing:
        return existing
    if os.name != "nt":
        return None

    target = data_path("cloudflared.exe")
    partial = target.with_suffix(".part")

    def say(text):
        if on_progress:
            try:
                on_progress(text)
            except Exception:
                pass

    try:
        import urllib.request

        say("cloudflared indiriliyor (51 MB, tek seferlik)...")
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(CLOUDFLARED_URL, timeout=120) as resp:
            with open(partial, "wb") as out:
                while True:
                    chunk = resp.read(1024 * 512)
                    if not chunk:
                        break
                    out.write(chunk)
        # Cloudflare'in resmi imzali ikilisi mi? Degilse KULLANMA.
        check = run_quiet(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-AuthenticodeSignature '{partial}').Status"],
            timeout=60,
        )
        status = (check.stdout or "").strip()
        if status != "Valid":
            partial.unlink(missing_ok=True)
            say(f"cloudflared imzasi dogrulanamadi ({status or 'bilinmiyor'})")
            return None
        partial.replace(target)
        say("cloudflared hazir")
        return str(target)
    except Exception as exc:
        try:
            partial.unlink(missing_ok=True)
        except Exception:
            pass
        say(f"cloudflared indirilemedi: {exc}")
        return None


def remote_access_enabled() -> bool:
    """
    Internet uzerinden erisim (tunel) VARSAYILAN OLARAK ACIKTIR.

    Kapaliyken telefon yalnizca ayni Wi-Fi agindan baglanabiliyor ve
    kendinden imzali sertifika yuzunden tarayici uyari veriyor.
    config/api_keys.json → "web_remote_access": false ile kapatilir.
    """
    value = get_app_config_value("web_remote_access", True)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "evet", "acik"}
    return bool(value)


# ── Yardimcilar ─────────────────────────────────────────────────────────────
def lan_ip() -> str:
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def read_token() -> str:
    try:
        cfg = json.loads(data_path("jarvis_web", "web_config.json").read_text(encoding="utf-8"))
        return str(cfg.get("token", "") or "")
    except Exception:
        return ""


def ensure_shared_token() -> str:
    """Sunucu, ajan ve arayuzun ORTAK token'i — artik BURADA uretilir.

    Eskiden token'i sunucu sureci uretip dosyaya yazar, arayuz de o dosyadan
    okurdu. Dosya yazilamayan bir kurulumda (izin, antivirus, salt-okunur
    klasor) arayuz bos token okuyor, telefona "?t=" ile biten yarim adres
    gidiyor ve telefon TOKEN SORUYORDU. Simdi token her durumda burada var;
    dosyaya yazmak sadece bir kolaylik (yeniden baslatinca ayni kalsin diye).
    """
    token = read_token()
    if not token:
        token = secrets.token_hex(16)
    try:
        path = data_path("jarvis_web", "web_config.json")
        cfg = {}
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        if cfg.get("token") != token:
            cfg["token"] = token
            path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass          # yazilamadi — sorun degil, ortam degiskeniyle tasiyoruz
    return token


def ensure_firewall_rule() -> bool:
    """Telefon ayni Wi-Fi'dan baglanabilsin diye gelen baglantiya izin ver.

    Windows disaridan gelen TCP baglantilarini varsayilan olarak engeller.
    Ilk calistirmada bir izin penceresi cikar; kullanici "Iptal" derse ya da
    pencereyi hic gormezse telefon sunucuya ULASAMAZ — bu PC'de test edildiginde
    fark edilmez, cunku tarayici ayni makinededir.

    Kural eklemek yonetici yetkisi ister. Yetki yoksa sessizce False doner;
    arayuz o zaman kullaniciya guvenlik duvarini kontrol etmesini soyler.
    """
    if os.name != "nt":
        return True
    name = "JARVIS Telefon"

    # 1) Kural zaten var mi?
    try:
        check = run_quiet(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
            timeout=15,
        )
        if check.returncode == 0 and str(SERVER_PORT) in (check.stdout or ""):
            return True
    except Exception:
        pass

    # 2) Guvenlik duvari komple kapaliysa engel yok — uyariyla korkutma.
    #    (Bu gelistirme makinesinde durum boyleydi; sorunun neden burada
    #    hic gorunmedigini aciklayan sebeplerden biri.)
    try:
        state = run_quiet(["netsh", "advfirewall", "show", "allprofiles", "state"],
                          timeout=15)
        # "State  OFF" / "Durum  KAPALI" satirlarini ayikla. Metnin tamaminda
        # "ON" aramak yaniltir ("Configuration" gibi kelimeler eslesir).
        marks = []
        for line in (state.stdout or "").splitlines():
            words = line.strip().upper().split()
            if words and words[0] in ("STATE", "DURUM"):
                marks.append(words[-1])
        if state.returncode == 0 and marks and not any(
                m in ("ON", "AÇIK", "ACIK") for m in marks):
            return True
    except Exception:
        pass

    # 3) Kurali eklemeyi dene — yonetici degilsek basarisiz olur.
    try:
        added = run_quiet(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={name}", "dir=in", "action=allow", "protocol=TCP",
             f"localport={SERVER_PORT}-{HTTPS_PORT}", "profile=any"],
            timeout=15,
        )
        return added.returncode == 0
    except Exception:
        return False


def _wait_for_port(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except Exception:
            time.sleep(0.4)
    return False


def _read_tunnel_url(log_path: Path) -> str:
    try:
        match = TUNNEL_RE.search(log_path.read_text(encoding="utf-8", errors="replace"))
        return match.group(0) if match else ""
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════
#  Arayuzden yonetilebilen sunucu
# ═══════════════════════════════════════════════════════════════════════════
class PhoneServer:
    """
    Telefon sunucusunu baslatir/durdurur ve adres+token bilgisini tutar.

    start() ANINDA doner; asil is arka plan thread'inde yurur ve her asamada
    on_update(durum_sozlugu) cagrilir. Boylece arayuz donmaz.
    """

    def __init__(self):
        self._procs: list[subprocess.Popen] = []
        self._lock = threading.Lock()
        self.state = "stopped"          # stopped | starting | running | error
        self.message = ""
        self.url = ""                   # telefona verilecek tam adres
        self.token = ""
        self.tunnel_url = ""            # internet adresi (varsa)
        self.lan_url = ""
        self.https_ready = False        # 8766 dinliyor mu (LAN icin sart)

    # ── durum ────────────────────────────────────────────────────────────
    def is_running(self) -> bool:
        with self._lock:
            return any(p.poll() is None for p in self._procs)

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "message": self.message,
            "url": self.url,
            "token": self.token,
            "tunnel": bool(self.tunnel_url),
            "lan_url": self.lan_url,
        }

    # ── baslat ───────────────────────────────────────────────────────────
    def start(self, on_update=None):
        if self.state in ("starting", "running"):
            return
        self.state = "starting"
        self.message = "Sunucu baslatiliyor..."
        if on_update:
            on_update(self.snapshot())
        threading.Thread(target=self._start_worker, args=(on_update,), daemon=True).start()

    def _notify(self, on_update, message=None):
        if message is not None:
            self.message = message
        if on_update:
            try:
                on_update(self.snapshot())
            except Exception:
                pass

    def _start_worker(self, on_update):
        logs = _log_dir()
        try:
            with self._lock:
                self._procs = []

            # Token'i BURADA uret ve alt sureclere ortam degiskeniyle ver.
            # Boylece dosya yazilamasa bile sunucu, ajan ve QR ayni token'i
            # kullanir (telefonun token sormasinin kok sebebi buydu).
            self.token = ensure_shared_token()
            child_env = {"JARVIS_WEB_TOKEN": self.token}

            server = _spawn("--web-server", logs / "server.log", child_env)
            with self._lock:
                self._procs.append(server)

            if not _wait_for_port(SERVER_PORT, timeout=45):
                self.state = "error"
                self._notify(on_update, f"Sunucu baslamadi. Gunluk: {logs / 'server.log'}")
                self.stop()
                return

            self._notify(on_update, "Ajan baglaniyor...")
            agent = _spawn("--web-agent", logs / "agent.log", child_env)
            with self._lock:
                self._procs.append(agent)
            time.sleep(1.2)

            ip = lan_ip()
            self.lan_url = f"https://{ip}:{HTTPS_PORT}/?t={self.token}"
            # HTTPS dinleyici gercekten acildi mi? Telefon mikrofonu yalnizca
            # guvenli baglamda calisir; acilmadiysa LAN secenegi ise yaramaz.
            self.https_ready = _wait_for_port(HTTPS_PORT, timeout=20)

            # Tunel (opsiyonel, varsayilan kapali)
            self.tunnel_url = ""
            if remote_access_enabled():
                # Kaynak surumde cloudflared paketle gelmez; yoksa indir.
                # Indirmezsek LAN + kendinden imzali sertifikaya duseriz ve
                # telefonda WebSocket kurulamaz (sayfa acilir, baglanti kopar).
                cloudflared = ensure_cloudflared(
                    lambda text: self._notify(on_update, text)
                )
                if cloudflared:
                    self._notify(on_update, "Internet tuneli aciliyor...")
                    tunnel_log = logs / "tunnel.log"
                    handle = open(tunnel_log, "w", encoding="utf-8", errors="replace")
                    kwargs = {"stdout": handle, "stderr": subprocess.STDOUT}
                    if os.name == "nt":
                        kwargs["creationflags"] = 0x08000000
                    tunnel = subprocess.Popen(
                        [cloudflared, "tunnel", "--url", f"http://localhost:{SERVER_PORT}"],
                        **kwargs,
                    )
                    with self._lock:
                        self._procs.append(tunnel)
                    for _ in range(45):
                        time.sleep(1.0)
                        self.tunnel_url = _read_tunnel_url(tunnel_log)
                        if self.tunnel_url:
                            break

            if self.tunnel_url:
                self.url = f"{self.tunnel_url}/?t={self.token}"
                self.state = "running"
                self._notify(on_update, "Internet uzerinden erisilebilir")
                return

            # ── Tunel yok → AYNI Wi-Fi ────────────────────────────────────
            # Once "tunel kurulamadiysa hata ver, LAN'a dusme" deniyordu;
            # cunku LAN kendinden imzali sertifika kullanir ve telefonda
            # uyari cikar. Ama hic baglanamamaktansa uyariyi bir kez gecip
            # baglanmak cok daha iyi: sayfa da WebSocket de AYNI adres ve
            # AYNI portu (8766) kullandigi icin kabul edilen istisna
            # ikisini birden kapsar.
            if not self.https_ready:
                # Bu durumda LAN adresi vermek anlamsiz: telefon sayfayi
                # acsa bile mikrofon acilmaz.
                self.state = "error"
                self._notify(
                    on_update,
                    f"HTTPS baslatilamadi — gunluge bak: {logs / 'server.log'}",
                )
                self.stop()
                return

            firewall_ok = ensure_firewall_rule()
            self.url = self.lan_url
            self.state = "running"
            if not remote_access_enabled():
                note = "Ayni Wi-Fi agindan erisilebilir"
            else:
                note = "Internet tuneli yok — AYNI Wi-Fi'dan baglan"
            if not firewall_ok:
                note += " (guvenlik duvari sorarsa IZIN VER)"
            self._notify(on_update, note)
        except Exception as exc:
            self.state = "error"
            self._notify(on_update, f"Hata: {exc}")
            self.stop()

    # ── durdur ───────────────────────────────────────────────────────────
    def stop(self, on_update=None):
        with self._lock:
            procs = list(self._procs)
            self._procs = []
        for proc in procs:
            _kill_tree(proc)
        # Kapanmayanlari zorla
        time.sleep(0.4)
        for proc in procs:
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        self.state = "stopped"
        self.message = "Durduruldu"
        self.url = self.tunnel_url = self.lan_url = ""
        self.https_ready = False
        if on_update:
            try:
                on_update(self.snapshot())
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
#  Konsol orkestratoru (TELEFON.bat)
# ═══════════════════════════════════════════════════════════════════════════
def _print_qr(url: str) -> None:
    try:
        import qrcode
    except ImportError:
        return
    try:
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make()
        print("   Telefon kamerasi ile bu QR kodu okut:\n")
        qr.print_ascii(invert=True)
    except Exception:
        pass


def run_orchestrator() -> int:
    server = PhoneServer()
    done = threading.Event()

    def on_update(info):
        if info["state"] in ("running", "error"):
            done.set()

    print()
    print("=" * 60)
    print("        J.A.R.V.I.S  WEB  —  Baslatiliyor...")
    print("=" * 60)
    print()

    server.start(on_update)
    while not done.wait(1.0):
        pass

    if server.state != "running":
        print(server.message)
        server.stop()
        return 1

    print()
    print("=" * 60)
    print("              J.A.R.V.I.S  WEB  —  HAZIR")
    print("=" * 60)
    print()
    print("TELEFONDAN AC (token gomulu, otomatik baglanir):")
    print()
    print(f"   {server.url}")
    print()
    _print_qr(server.url)
    print()
    print("-" * 60)
    if server.tunnel_url:
        print("Bu adres INTERNET uzerinden erisilebilir (her yerden calisir).")
        print(f"Yerel ag adresi : {server.lan_url}")
    else:
        print("Bu adres yalnizca AYNI Wi-Fi agindan calisir.")
        print("Telefon bu bilgisayarla AYNI aga bagli olmali (hucresel veri KAPALI).")
        print("Ilk acilista tarayici 'baglantiniz ozel degil' uyarisi verir:")
        print("  Android/Chrome : Gelismis → Yine de devam et")
        print("  iPhone/Safari  : Ayrintilar → Bu siteyi ziyaret et")
        print("Bu normaldir — sertifika bu bilgisayarin kendi uretimi.")
        if not remote_access_enabled():
            print()
            print("Her yerden baglanmak istersen config/api_keys.json icine")
            print('  "web_remote_access": true  ekleyip tekrar baslat.')
    print("-" * 60)
    print("GUVENLIK: Bu adres/QR bir SIFRE gibidir — bilgisayarina tam")
    print("   erisim verir. VIDEODA GOSTERME / kimseyle paylasma.")
    print("-" * 60)
    print()
    print("Bu pencereyi KAPATMA — kapatinca JARVIS Web durur.")
    print("Durdurmak icin: Ctrl+C")
    print()

    try:
        while server.is_running():
            time.sleep(2)
        print("Sunucu durdu.")
    except KeyboardInterrupt:
        print("\nKapatiliyor...")
    finally:
        server.stop()
    return 0
