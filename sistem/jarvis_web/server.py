#!/usr/bin/env python3
"""
JARVIS Web — Backend sunucusu
─────────────────────────────
Web istemcileri (telefon/bilgisayar tarayıcısı) ile Gemini Live arasında
köprü kurar. bilgisayar ajanı bağlıysa sistem araçlarını (uygulama açma, takvim,
shell...) ona yönlendirir.

Çalıştırma:
    python3 server.py                  # http://0.0.0.0:8765
    python3 server.py --ssl            # https (telefon mikrofonu için gerekli)
    python3 server.py --port 9000

İlk çalıştırmada erişim token'ı üretilir ve ekrana basılır.
"""

from __future__ import annotations

import os
import sys

import asyncio
import argparse
import datetime
import json
import secrets
import subprocess
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from google import genai
from google.genai import types

# ── Ana proje modüllerine erişim (aynı makinede çalışırken) ─────────────────
WEB_DIR  = Path(__file__).resolve().parent
BASE_DIR = WEB_DIR.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from tool_defs import TOOL_DECLARATIONS
except Exception:
    TOOL_DECLARATIONS = []
    print("[UYARI] tool_defs bulunamadı — araçsız modda çalışılıyor.")

try:
    from app_config import get_app_config_value
except Exception:
    def get_app_config_value(key, default=None):
        import os
        if key == "gemini_api_key":
            return os.environ.get("GEMINI_API_KEY", "")
        return default

try:
    from memory.memory_manager import (
        load_memory, update_memory, delete_memory, format_memory_for_prompt,
    )
    MEMORY_OK = True
except Exception:
    MEMORY_OK = False

try:
    from actions.weather import get_weather_summary
    WEATHER_OK = True
except Exception:
    WEATHER_OK = False

# ── Mod ──────────────────────────────────────────────────────────────────────
# PUBLIC (herkese açık bulut): her kullanıcı KENDİ Gemini anahtarını girer,
#   bilgisayar/Mac kontrolü YOK, yalnızca bulut araçları. Ortak token yok.
# ÖZEL (varsayılan): sahibin anahtarı config'ten, bilgisayar ajanı + tüm araçlar,
#   ortak token ile korunur.
PUBLIC_MODE = os.environ.get("JARVIS_PUBLIC") == "1"

# ── Sabitler ─────────────────────────────────────────────────────────────────
LIVE_MODEL  = "models/gemini-2.5-flash-native-audio-latest"
try:
    from app_paths import data_path, resource_path

    PROMPT_PATH = resource_path("core", "prompt.txt")      # salt-okunur kaynak
    CONFIG_PATH = data_path("jarvis_web", "web_config.json")  # token → yazilabilir
except Exception:
    PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"
    CONFIG_PATH = WEB_DIR / "web_config.json"

# Sunucuda (bulutta da çalışabilen) araçlar
SERVER_TOOLS = {"get_weather", "save_memory", "delete_memory"}
# Tarayıcıya yönlendirilen araçlar
CLIENT_TOOLS = {"toggle_webcam"}
# Geri kalan her şey → bilgisayar ajanı
# Herkese açık modda İZİN VERİLEN araçlar (bilgisayar/hesap kontrolü hariç)
PUBLIC_TOOLS = {"get_weather", "toggle_webcam"}

AGENT_TOOL_TIMEOUT = 60  # shell / takvim helper'ları yavaş olabilir


# ── Yapılandırma ─────────────────────────────────────────────────────────────
def load_web_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ensure_token() -> str:
    """Erişim token'ı: önce başlatıcının verdiği, sonra dosyadaki, yoksa yeni.

    JARVIS_WEB_TOKEN neden var: Token'ı eskiden yalnızca bu süreç üretip
    dosyaya yazıyordu, arayüz de o dosyadan okuyordu. Dosya yazılamazsa
    (salt-okunur klasör, izin sorunu, antivirüs) token bellekte kalıyor,
    arayüz boş okuyor ve telefona ?t= ile biten adres gidiyordu — telefon
    da token SORUYORDU. Artık token'ı başlatıcı üretip ortam değişkeniyle
    hem sunucuya hem ajana veriyor; dosya sadece yedek.
    """
    env_token = str(os.environ.get("JARVIS_WEB_TOKEN", "") or "").strip()
    if env_token:
        return env_token

    cfg = load_web_config()
    token = str(cfg.get("token", "") or "").strip()
    if not token:
        token = secrets.token_hex(16)
        cfg["token"] = token
        try:
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass  # salt-okunur/geçici bulut FS — token bellek içinde kalır
    return token


# Herkese açık modda ortak token yok (herkesin anahtarı kendi kimliği)
TOKEN = "" if PUBLIC_MODE else ensure_token()


def get_api_key() -> str:
    return str(get_app_config_value("gemini_api_key", "") or "")


def load_system_prompt() -> str:
    try:
        from prompt_loader import adapt_prompt

        base = adapt_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
    except Exception:
        base = (
            "Sen JARVIS'sin — kişisel AI asistanı. Türkçe konuş. "
            "Kısa ve net yanıtlar ver. Araçları kullanarak görevleri tamamla."
        )
    if PUBLIC_MODE:
        web_ctx = (
            "\n\n[WEB — HERKESE AÇIK MOD]\n"
            "Kullanıcı sana telefon/bilgisayar tarayıcısından bağlanıyor. "
            "Bu sürümde bir bilgisayarı kontrol EDEMEZSİN: uygulama açma, shell, "
            "takvim, ekran gibi araçlar YOK. Sohbet edebilir, kullanıcının "
            "kamerasıyla görebilir (toggle_webcam) ve hava durumu verebilirsin. "
            "Biri senden bilgisayar kontrolü isterse, bunun yalnızca masaüstü "
            "JARVIS sürümünde olduğunu kibarca söyle."
        )
    else:
        web_ctx = (
            "\n\n[WEB MODU]\n"
            "Kullanıcı sana tarayıcıdan (telefon veya bilgisayar) bağlanıyor. "
            "Sistem araçları (uygulama açma, takvim, shell, ekran analizi...) "
            "kullanıcının bilgisayarında çalışan ajan üzerinden yürütülür. "
            "Bir araç 'Bilgisayar bağlı değil' hatası dönerse bunu kullanıcıya "
            "kibarca açıkla; bilgisayarı açıksa JARVIS ajanını başlatması gerektiğini söyle. "
            "toggle_webcam aracı kullanıcının TARAYICISINDAKİ kamerayı açar."
        )
    return base + web_ctx


# ── Mac Ajan Hub'ı ───────────────────────────────────────────────────────────
class AgentHub:
    """Tek bilgisayar ajanının bağlantısını ve bekleyen araç çağrılarını yönetir."""

    def __init__(self):
        self.ws: WebSocket | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self.lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self.ws is not None

    async def attach(self, ws: WebSocket):
        async with self.lock:
            old = self.ws
            self.ws = ws
        if old is not None:
            try:
                await old.close()
            except Exception:
                pass

    async def detach(self, ws: WebSocket):
        async with self.lock:
            if self.ws is ws:
                self.ws = None
        for fut in self.pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Ajan bağlantısı koptu"))
        self.pending.clear()

    async def call_tool(self, name: str, args: dict) -> str:
        if self.ws is None:
            return (
                "Bilgisayar bağlı değil — bu işlem için bilgisayarın açık ve "
                "JARVIS ajanının (agent.py) çalışıyor olması gerekiyor."
            )
        call_id = uuid.uuid4().hex
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self.pending[call_id] = fut
        try:
            await self.ws.send_text(json.dumps(
                {"type": "tool_call", "id": call_id, "name": name, "args": args}
            ))
            return str(await asyncio.wait_for(fut, timeout=AGENT_TOOL_TIMEOUT))
        except asyncio.TimeoutError:
            return f"Araç zaman aşımına uğradı: {name}"
        except ConnectionError:
            return "Bilgisayar bağlantısı araç çalışırken koptu."
        finally:
            self.pending.pop(call_id, None)

    def resolve(self, call_id: str, result: str):
        fut = self.pending.get(call_id)
        if fut and not fut.done():
            fut.set_result(result)


agent_hub = AgentHub()
web_clients: "set[LiveBridge]" = set()


async def broadcast_agent_status():
    msg = json.dumps({"type": "agent_status", "connected": agent_hub.connected})
    for bridge in list(web_clients):
        try:
            await bridge.ws.send_text(msg)
        except Exception:
            pass


# ── Sunucu tarafı araçlar ────────────────────────────────────────────────────
async def run_server_tool(name: str, args: dict) -> str:
    loop = asyncio.get_event_loop()
    try:
        if name == "get_weather":
            if not WEATHER_OK:
                return "Hava durumu modülü sunucuda mevcut değil."
            return await loop.run_in_executor(
                None, lambda: get_weather_summary(args.get("location") or None)
            ) or "Hava durumu alındı."

        if name == "save_memory":
            if not MEMORY_OK:
                return "Bellek modülü sunucuda mevcut değil."
            cat = args.get("category", "notes")
            key = args.get("key", "")
            val = args.get("value", "")
            if key and val:
                update_memory({cat: {key: {"value": val}}})
            return "ok"

        if name == "delete_memory":
            if not MEMORY_OK:
                return "Bellek modülü sunucuda mevcut değil."
            return delete_memory(
                args.get("category", ""),
                args.get("key", ""),
                args.get("match_text", ""),
            )
    except Exception as e:
        return f"Hata: {e}"
    return f"Bilinmeyen sunucu aracı: {name}"


# ── Gemini Live köprüsü (istemci başına bir oturum) ─────────────────────────
class LiveBridge:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.session = None

    def _build_config(self) -> types.LiveConnectConfig:
        parts = [
            f"[ŞU ANKİ ZAMAN]\n{datetime.datetime.now().strftime('%A, %d %B %Y — %H:%M')}\n\n"
        ]
        # Ortak hafıza yalnızca özel modda (çok kullanıcılı bulutta paylaşılmaz)
        if MEMORY_OK and not PUBLIC_MODE:
            try:
                mem_str = format_memory_for_prompt(load_memory())
                if mem_str:
                    parts.append(mem_str + "\n\n")
            except Exception:
                pass
        parts.append(load_system_prompt())

        # Herkese açık modda yalnızca bulut araçları göster
        decls = TOOL_DECLARATIONS
        if PUBLIC_MODE:
            decls = [d for d in TOOL_DECLARATIONS if d.get("name") in PUBLIC_TOOLS]

        voice = "Charon" if PUBLIC_MODE else str(
            get_app_config_value("voice", "Charon") or "Charon")

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": decls}],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice
                    )
                )
            ),
        )

    async def send_json(self, payload: dict):
        try:
            await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    async def _await_client_api_key(self) -> str:
        """Herkese açık modda: istemcinin gönderdiği Gemini anahtarını bekler."""
        await self.send_json({"type": "need_key"})
        while True:
            msg = await self.ws.receive()
            if msg.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()
            text = msg.get("text")
            if not text:
                continue
            try:
                obj = json.loads(text)
            except Exception:
                continue
            if obj.get("type") == "apikey":
                key = str(obj.get("key", "") or "").strip()
                if key:
                    return key
                await self.send_json({"type": "error",
                                      "text": "API anahtarı boş."})

    async def run(self):
        if PUBLIC_MODE:
            # Her kullanıcı kendi anahtarını girer; sunucuda saklanmaz
            api_key = await self._await_client_api_key()
        else:
            api_key = get_api_key()
            if not api_key:
                await self.send_json({"type": "error",
                                      "text": "Gemini API anahtarı bulunamadı."})
                return

        client = genai.Client(api_key=api_key,
                              http_options={"api_version": "v1alpha"})

        try:
            async with client.aio.live.connect(
                model=LIVE_MODEL, config=self._build_config()
            ) as session:
                self.session = session
                await self.send_json({"type": "ready"})
                await self.send_json({"type": "agent_status",
                                      "connected": (not PUBLIC_MODE) and agent_hub.connected})

                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._from_browser())
                    tg.create_task(self._from_gemini())
        except Exception as e:
            # Geçersiz anahtar / bağlantı hatası — istemciye bildir
            msg = str(e)
            if "API" in msg or "key" in msg.lower() or "auth" in msg.lower() \
               or "invalid" in msg.lower() or "permission" in msg.lower():
                await self.send_json({"type": "error",
                    "text": "API anahtarı geçersiz görünüyor. Kontrol edip tekrar dene."})
            else:
                await self.send_json({"type": "error",
                    "text": "Bağlantı hatası. Tekrar denenecek."})
            raise

    # Tarayıcıdan gelenler → Gemini
    async def _from_browser(self):
        while True:
            msg = await self.ws.receive()
            if msg.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()

            data: bytes | None = msg.get("bytes")
            if data:
                kind, payload = data[0], data[1:]
                if kind == 0x01:    # mikrofon PCM16 @16k
                    await self.session.send_realtime_input(
                        audio=types.Blob(data=payload,
                                         mime_type="audio/pcm;rate=16000"))
                elif kind == 0x02:  # kamera JPEG karesi
                    await self.session.send_realtime_input(
                        media={"data": payload, "mime_type": "image/jpeg"})
                continue

            text = msg.get("text")
            if not text:
                continue
            try:
                obj = json.loads(text)
            except Exception:
                continue
            if obj.get("type") == "text" and obj.get("text", "").strip():
                await self.session.send_client_content(
                    turns={"parts": [{"text": obj["text"].strip()}]},
                    turn_complete=True,
                )

    # Gemini'den gelenler → tarayıcı
    async def _from_gemini(self):
        in_buf:  list[str] = []
        out_buf: list[str] = []
        while True:
            async for response in self.session.receive():
                if response.data:
                    try:
                        await self.ws.send_bytes(response.data)
                    except Exception:
                        return

                sc = response.server_content
                if sc:
                    if getattr(sc, "interrupted", False):
                        await self.send_json({"type": "interrupt"})
                    if sc.output_transcription and sc.output_transcription.text:
                        out_buf.append(sc.output_transcription.text.strip())
                    if sc.input_transcription and sc.input_transcription.text:
                        in_buf.append(sc.input_transcription.text.strip())
                    if sc.turn_complete:
                        full_in = " ".join(t for t in in_buf if t).strip()
                        if full_in:
                            await self.send_json({"type": "log",
                                                  "who": "user", "text": full_in})
                        in_buf = []
                        full_out = " ".join(t for t in out_buf if t).strip()
                        if full_out:
                            await self.send_json({"type": "log",
                                                  "who": "jarvis", "text": full_out})
                        out_buf = []
                        await self.send_json({"type": "turn_complete"})

                if response.tool_call:
                    responses = []
                    for fc in response.tool_call.function_calls:
                        result = await self._dispatch_tool(fc.name,
                                                           dict(fc.args or {}))
                        responses.append(types.FunctionResponse(
                            id=fc.id, name=fc.name,
                            response={"result": result}))
                    await self.session.send_tool_response(
                        function_responses=responses)

    async def _dispatch_tool(self, name: str, args: dict) -> str:
        print(f"[Sunucu] 🔧 {name} {args}")
        await self.send_json({"type": "tool", "name": name})

        # Herkese açık modda bilgisayar/hesap araçları kapalı
        if PUBLIC_MODE and name not in PUBLIC_TOOLS:
            return ("Bu özellik web sürümünde yok — sadece bilgisayardaki "
                    "masaüstü JARVIS bunu yapabilir.")

        if name in SERVER_TOOLS:
            result = await run_server_tool(name, args)
        elif name in CLIENT_TOOLS:
            action = str(args.get("action", "start")).strip().lower()
            await self.send_json({"type": "webcam", "action": action})
            result = ("Webcam akışı başlatıldı — tarayıcı kamerası açılıyor."
                      if action == "start" else "Webcam akışı durduruldu.")
        else:
            result = await agent_hub.call_tool(name, args)

        print(f"[Sunucu] 📤 {name} → {str(result)[:80]}")
        return result


# ── FastAPI uygulaması ───────────────────────────────────────────────────────
app = FastAPI(title="JARVIS Web")


@app.get("/")
async def index():
    # Telefon tarayicisi ESKI app.js'i onbellekten sunmasin: her surumde
    # adres degissin. Yoksa duzeltilmis sunum yuklendigi halde telefon
    # eski davranisi (token sorma vb.) surdurebiliyor.
    try:
        from version import BUILD
    except Exception:
        BUILD = "0"
    html = (WEB_DIR / "static" / "index.html").read_text(encoding="utf-8")
    html = (html
            .replace("/static/app.js", f"/static/app.js?v={BUILD}")
            .replace("/static/style.css", f"/static/style.css?v={BUILD}"))
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/mode")
async def mode():
    # İstemci: public ise kendi API anahtarını sorar, değilse token akışı
    # build: telefonda hangi sürümün açıldığı görünsün (eski kurulumu
    # çalıştırıp "düzelmemiş" sanmayı önler)
    try:
        from version import STAMP
    except Exception:
        STAMP = ""
    return {"public": PUBLIC_MODE, "build": STAMP}


app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


def _check_token(ws: WebSocket) -> bool:
    # Herkese açık modda ortak token yok — herkes kendi API anahtarıyla girer
    if PUBLIC_MODE:
        return True
    return ws.query_params.get("token", "") == TOKEN


@app.websocket("/ws/client")
async def ws_client(ws: WebSocket):
    if not _check_token(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    bridge = LiveBridge(ws)
    web_clients.add(bridge)
    print(f"[Sunucu] 🌐 Web istemcisi bağlandı ({len(web_clients)} aktif)")
    try:
        await bridge.run()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        traceback.print_exc()
    finally:
        web_clients.discard(bridge)
        print(f"[Sunucu] 🌐 Web istemcisi ayrıldı ({len(web_clients)} aktif)")


@app.websocket("/ws/agent")
async def ws_agent(ws: WebSocket):
    # Herkese açık bulutta bilgisayar ajanı yok — bağlantıyı reddet
    if PUBLIC_MODE:
        await ws.close(code=4403)
        return
    if ws.query_params.get("token", "") != TOKEN:
        await ws.close(code=4401)
        return
    await ws.accept()
    await agent_hub.attach(ws)
    print("[Sunucu] 💻 bilgisayar ajanı bağlandı")
    await broadcast_agent_status()
    try:
        while True:
            text = await ws.receive_text()
            try:
                obj = json.loads(text)
            except Exception:
                continue
            if obj.get("type") == "tool_result":
                agent_hub.resolve(obj.get("id", ""), obj.get("result", ""))
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        await agent_hub.detach(ws)
        print("[Sunucu] 💻 bilgisayar ajanı ayrıldı")
        await broadcast_agent_status()


# ── SSL sertifikası (telefon mikrofonu https ister) ─────────────────────────
def _cert_dir() -> Path:
    # .exe olarak paketlendiginde WEB_DIR paketin ICIDIR ve salt okunurdur;
    # sertifika yazilabilir veri koküne uretilmeli.
    try:
        from app_paths import data_path

        return data_path("jarvis_web", "certs")
    except Exception:
        return WEB_DIR / "certs"


def _cert_covers(crt: Path, ip: str) -> bool:
    """Mevcut sertifika hâlâ geçerli ve BU LAN IP'sini kapsıyor mu?

    IP kontrolü şart: Wi-Fi ağı ya da DHCP kirası değişince bilgisayarın
    adresi değişir. Eski sertifika yeni adresi içermediği için telefon
    "bu sertifika bu site için değil" der; bazı tarayıcılar o durumda
    "yine de devam et" seçeneğini bile göstermez.
    """
    try:
        import ipaddress
        from cryptography import x509

        cert = x509.load_pem_x509_certificate(crt.read_bytes())
        if cert.not_valid_after_utc <= datetime.datetime.now(datetime.timezone.utc):
            return False
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value
        covered = {str(v) for v in san.get_values_for_type(x509.IPAddress)}
        ipaddress.ip_address(ip)          # ip gecerli mi
        return ip in covered
    except Exception:
        return False


def _write_self_signed(crt: Path, key: Path, ip: str) -> None:
    """Sertifikayı Python içinden üret — openssl KURULU OLMAK ZORUNDA DEĞİL.

    NEDEN: Eskiden `openssl` komutu çağrılıyordu. macOS'ta openssl her zaman
    vardır, temiz bir Windows'ta YOKTUR (bu makinede yalnızca Git for Windows
    kurulu olduğu için vardı). openssl bulunamayınca HTTPS dinleyici hiç
    açılmıyor, telefon da mikrofonu yalnızca güvenli bağlamda (https)
    açabildiği için aynı Wi-Fi üzerinden bağlanmak imkânsız hâle geliyordu.

    Ayrıca IP'yi SubjectAltName'e yazıyoruz; eski sertifikanın yalnızca
    CN=jarvis.local olması mobil tarayıcılarda ek uyarı sebebiydi.
    """
    import ipaddress

    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    pkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "JARVIS")])

    alt: list = [x509.DNSName("localhost")]
    for candidate in ("127.0.0.1", ip):
        try:
            entry = x509.IPAddress(ipaddress.ip_address(candidate))
            if entry not in alt:
                alt.append(entry)
        except Exception:
            pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(pkey.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None),
                       critical=True)
        .sign(pkey, hashes.SHA256())
    )

    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key.write_bytes(pkey.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))


def ensure_ssl_cert(ip: str = "") -> tuple[str, str]:
    cert_dir = _cert_dir()
    cert_dir.mkdir(parents=True, exist_ok=True)
    crt = cert_dir / "jarvis.crt"
    key = cert_dir / "jarvis.key"

    if crt.exists() and key.exists() and (not ip or _cert_covers(crt, ip)):
        return str(crt), str(key)

    print(f"[Sunucu] 🔐 SSL sertifikası üretiliyor (IP {ip or '-'})...", flush=True)
    _write_self_signed(crt, key, ip)
    return str(crt), str(key)


def detect_lan_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "<mac-ip>"


def main():
    ap = argparse.ArgumentParser(description="JARVIS Web sunucusu")
    ap.add_argument("--host", default="0.0.0.0")
    # Bulut platformları portu PORT ortam değişkeniyle verir
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("PORT", "8765")),
                    help="HTTP portu; HTTPS bunun bir fazlasında açılır")
    ap.add_argument("--no-ssl", action="store_true",
                    help="HTTPS dinleyicisini kapat (telefon mikrofonu çalışmaz)")
    args = ap.parse_args()

    # ── Herkese açık bulut modu ──────────────────────────────
    if PUBLIC_MODE:
        print(flush=True)
        print("╔════════════════════════════════════════════════════╗", flush=True)
        print("║        J.A.R.V.I.S  WEB  —  HERKESE AÇIK MOD        ║", flush=True)
        print("╚════════════════════════════════════════════════════╝", flush=True)
        print(f"  Port  : {args.port}  (her kullanıcı kendi API anahtarını girer)", flush=True)
        print(flush=True)
        # Bulutta TLS'i platform/proxy sağlar → düz HTTP dinle
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
        return

    # ── Özel mod (sahibin bilgisayarı) ───────────────────────
    ip = detect_lan_ip()
    https_port = args.port + 1

    print(flush=True)
    print("╔════════════════════════════════════════════════════╗", flush=True)
    print("║              J.A.R.V.I.S  WEB SUNUCUSU              ║", flush=True)
    print("╚════════════════════════════════════════════════════╝", flush=True)
    print(f"  Bilgisayar : http://localhost:{args.port}", flush=True)
    if not args.no_ssl:
        print(f"  Telefon    : https://{ip}:{https_port}", flush=True)
        print(f"               (sertifika uyarısını kabul et)", flush=True)
    print(f"  Token      : {TOKEN}", flush=True)
    print(f"  Ajan       : {'python' if sys.platform == 'win32' else 'python3'} agent.py", flush=True)
    print(flush=True)

    async def serve_all():
        servers = [uvicorn.Server(uvicorn.Config(
            app, host=args.host, port=args.port, log_level="warning"))]
        if not args.no_ssl:
            try:
                crt, key = ensure_ssl_cert(ip)
                servers.append(uvicorn.Server(uvicorn.Config(
                    app, host=args.host, port=https_port, log_level="warning",
                    ssl_certfile=crt, ssl_keyfile=key)))
            except Exception as e:
                # Bu satir gunluge dusmezse HTTPS ayaktadir. Duserse telefon
                # ayni Wi-Fi uzerinden BAGLANAMAZ (mikrofon https ister).
                print(f"[Sunucu] ⚠️  SSL başlatılamadı ({e}) — sadece HTTP.",
                      flush=True)
        await asyncio.gather(*(s.serve() for s in servers))

    asyncio.run(serve_all())


if __name__ == "__main__":
    main()
