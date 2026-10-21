/* J.A.R.V.I.S Web istemcisi
   ─────────────────────────
   • WebSocket ile backend'e bağlanır (binary: ses, JSON: kontrol)
   • Mikrofon: AudioWorklet → 16 kHz PCM16 → [0x01 + payload]
   • Kamera : 1.5 s'de bir JPEG kare  → [0x02 + payload]
   • Hoparlör: sunucudan gelen 24 kHz PCM16'yı sırayla çalar
   • Orb    : canvas animasyonu — konuşurken nabız atar
*/

"use strict";

// ── Token ────────────────────────────────────────────────────────────────
// Öncelik sırası: URL parametresi (?t=...) → localStorage → soru.
// QR/link içine token gömülü gelirse telefon otomatik bağlanır, elle giriş yok.
function getToken() {
  const params = new URLSearchParams(location.search);
  const fromUrl = (params.get("t") || params.get("token") || "").trim();
  if (fromUrl) {
    try { localStorage.setItem("jarvis_token", fromUrl); } catch (e) {}
    // NOT: Token'ı adres çubuğundan SİLMİYORUZ. Silince şu durumlarda
    // kayboluyordu: sertifika uyarısını geçince sayfa yeniden yükleniyor,
    // kullanıcı sayfayı tazeliyor, ya da tarayıcı localStorage'a izin
    // vermiyor. Sonuçta telefon "token" soruyordu. Adresin kendisi zaten
    // gizli (QR ile geliyor), token'ı orada tutmak güvenliği değiştirmez.
    return fromUrl;
  }
  let t = "";
  try { t = localStorage.getItem("jarvis_token") || ""; } catch (e) {}
  if (!t) {
    t = (prompt(
      "JARVIS erişim token'ı:\n\n" +
      "(Bunu görmemen gerekiyordu — QR kodu okutursan token otomatik gelir. " +
      "Adresi elle yazdıysan sonundaki ?t=... kısmını da ekle.)"
    ) || "").trim();
    if (t) { try { localStorage.setItem("jarvis_token", t); } catch (e) {} }
  }
  return t;
}

// ── Durum ────────────────────────────────────────────────────────────────
const S = {
  ws: null,
  ready: false,
  micOn: false,
  camOn: false,
  audioCtx: null,        // yakalama (mic)
  playCtx: null,         // çalma (24k)
  workletNode: null,
  micStream: null,
  camStream: null,
  camTimer: null,
  nextPlayTime: 0,
  playingSources: [],
  outLevel: 0,           // orb nabzı için çıkış seviyesi
  speaking: false,
  reconnectDelay: 2000,  // başarısız denemede artan bekleme (backoff)
  fatalMsg: null,        // kalıcı hata (örn. API anahtarı yok)
  lastLogKey: "",        // aynı log satırını tekrar yazmamak için
  public: false,         // herkese açık bulut modu mu
  apiKey: "",            // public modda kullanıcının kendi Gemini anahtarı
  awaitingKey: false,    // anahtar ekranı açıkken reconnect'i durdur
  reconnectTimer: null,  // bekleyen reconnect zamanlayıcısı
};

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const logEl = $("log");

// ── Log ──────────────────────────────────────────────────────────────────
function addLog(who, text) {
  const key = who + "|" + text;
  if (key === S.lastLogKey) return;   // ardışık aynı satırı yazma (spam engeli)
  S.lastLogKey = key;
  const row = document.createElement("div");
  row.className = "row";
  const cls = who === "user" ? "who-user" : who === "jarvis" ? "who-jarvis" : "who-sys";
  const label = who === "user" ? "SİZ" : who === "jarvis" ? "JARVIS" : "SYS";
  row.innerHTML = `<span class="${cls}">${label}:</span> `;
  row.appendChild(document.createTextNode(text));
  logEl.appendChild(row);
  logEl.scrollTop = logEl.scrollHeight;
  while (logEl.children.length > 200) logEl.removeChild(logEl.firstChild);
}

function setStatus(text, live = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("live", live);
}

// ── WebSocket ────────────────────────────────────────────────────────────
function wsURL() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  // Herkese açık modda ortak token yok — kimlik kullanıcının kendi API anahtarı
  if (S.public) return `${proto}://${location.host}/ws/client`;
  return `${proto}://${location.host}/ws/client?token=${encodeURIComponent(getToken())}`;
}

function connect() {
  const ws = new WebSocket(wsURL());
  ws.binaryType = "arraybuffer";
  S.ws = ws;

  ws.onopen = () => {
    $("badge-server").className = "badge on";
    setStatus("GEMINI BAĞLANIYOR…");
  };

  ws.onclose = (e) => {
    $("badge-server").className = "badge off";
    $("badge-agent").className = "badge off";
    S.ready = false;
    if (e.code === 4401) {
      localStorage.removeItem("jarvis_token");
      setStatus("TOKEN HATALI — yenilemek için sayfayı tazele");
      return;
    }
    // Anahtar ekranı açıksa (kullanıcı girişi bekleniyor) yeniden bağlanma
    if (S.awaitingKey) return;
    // Kalıcı hata varsa (anahtar yok vb.) onu göster, yoksa normal kopma mesajı
    setStatus(S.fatalMsg || "BAĞLANTI KOPTU — yeniden deneniyor…");
    // Art arda başarısızlıkta bekleme süresini artır (spam yerine sakin tekrar)
    S.reconnectDelay = Math.min(S.reconnectDelay * 1.6, 15000);
    S.reconnectTimer = setTimeout(connect, S.reconnectDelay);
  };

  ws.onmessage = (ev) => {
    if (ev.data instanceof ArrayBuffer) {
      playAudioChunk(ev.data);
      return;
    }
    let obj;
    try { obj = JSON.parse(ev.data); } catch { return; }

    switch (obj.type) {
      case "need_key":
        // Public mod: sunucu kendi API anahtarımızı istiyor
        S.ws.send(JSON.stringify({ type: "apikey", key: S.apiKey }));
        setStatus("GEMINI BAĞLANIYOR…");
        break;
      case "ready":
        S.ready = true;
        S.fatalMsg = null;
        S.reconnectDelay = 2000;      // başarılı bağlantı → backoff sıfırla
        setStatus("DİNLİYORUM", true);
        addLog("sys", "JARVIS hazır.");
        break;
      case "agent_status":
        $("badge-agent").className = "badge " + (obj.connected ? "on" : "off");
        break;
      case "log":
        addLog(obj.who, obj.text);
        break;
      case "tool":
        setStatus("ÇALIŞIYOR: " + obj.name, true);
        break;
      case "turn_complete":
        setStatus(S.micOn ? "DİNLİYORUM" : "HAZIR", true);
        break;
      case "interrupt":
        flushPlayback();
        break;
      case "webcam":
        if (obj.action === "start") startCam();
        else stopCam();
        break;
      case "error":
        S.fatalMsg = obj.text;         // kalıcı hata → kopunca da bunu göster
        addLog("sys", "HATA: " + obj.text);
        setStatus("HATA: " + obj.text);
        // Public modda anahtar geçersizse: kaydı sil, giriş ekranını göster
        if (S.public && /anahtar/i.test(obj.text)) {
          localStorage.removeItem("jarvis_gemini_key");
          S.apiKey = "";
          try { S.ws.close(); } catch {}
          showKeyScreen(obj.text);
        }
        break;
    }
  };
}

// ── Ses çalma (24 kHz PCM16) ─────────────────────────────────────────────
function ensurePlayCtx() {
  if (!S.playCtx) {
    S.playCtx = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 24000,
    });
  }
  if (S.playCtx.state === "suspended") S.playCtx.resume();
  return S.playCtx;
}

function playAudioChunk(buf) {
  const ctx = ensurePlayCtx();
  const i16 = new Int16Array(buf);
  if (i16.length === 0) return;

  const f32 = new Float32Array(i16.length);
  let peak = 0;
  for (let i = 0; i < i16.length; i++) {
    f32[i] = i16[i] / 32768;
    const a = Math.abs(f32[i]);
    if (a > peak) peak = a;
  }
  S.outLevel = Math.max(S.outLevel, peak);

  const audioBuf = ctx.createBuffer(1, f32.length, 24000);
  audioBuf.copyToChannel(f32, 0);

  const src = ctx.createBufferSource();
  src.buffer = audioBuf;
  src.connect(ctx.destination);

  const now = ctx.currentTime;
  if (S.nextPlayTime < now) S.nextPlayTime = now + 0.04;
  src.start(S.nextPlayTime);
  S.nextPlayTime += audioBuf.duration;

  S.playingSources.push(src);
  src.onended = () => {
    const idx = S.playingSources.indexOf(src);
    if (idx >= 0) S.playingSources.splice(idx, 1);
    if (S.playingSources.length === 0) S.speaking = false;
  };
  S.speaking = true;
}

function flushPlayback() {
  for (const src of S.playingSources) {
    try { src.stop(); } catch {}
  }
  S.playingSources = [];
  S.nextPlayTime = 0;
  S.speaking = false;
}

// ── Mikrofon ─────────────────────────────────────────────────────────────
async function startMic() {
  if (S.micOn) return;
  try {
    S.micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
  } catch {
    addLog("sys", "Mikrofon izni reddedildi.");
    return;
  }

  S.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (S.audioCtx.state === "suspended") await S.audioCtx.resume();
  await S.audioCtx.audioWorklet.addModule("/static/pcm-worklet.js");

  const srcNode = S.audioCtx.createMediaStreamSource(S.micStream);
  S.workletNode = new AudioWorkletNode(S.audioCtx, "pcm-capture");

  S.workletNode.port.onmessage = (ev) => {
    if (!S.ws || S.ws.readyState !== WebSocket.OPEN || !S.ready) return;
    const i16 = ev.data; // Int16Array
    const out = new Uint8Array(1 + i16.byteLength);
    out[0] = 0x01;
    out.set(new Uint8Array(i16.buffer, i16.byteOffset, i16.byteLength), 1);
    S.ws.send(out);
  };

  srcNode.connect(S.workletNode);
  // Worklet'i canlı tutmak için sessiz bağlantı
  const silent = S.audioCtx.createGain();
  silent.gain.value = 0;
  S.workletNode.connect(silent).connect(S.audioCtx.destination);

  ensurePlayCtx(); // kullanıcı jesti varken çalma context'ini de aç (iOS)

  S.micOn = true;
  $("btn-mic").className = "ctl rec";
  $("btn-mic").textContent = "🔴 MIC ON";
  setStatus("DİNLİYORUM", true);
}

function stopMic() {
  if (S.micStream) S.micStream.getTracks().forEach((t) => t.stop());
  if (S.workletNode) { try { S.workletNode.disconnect(); } catch {} }
  if (S.audioCtx) { try { S.audioCtx.close(); } catch {} }
  S.micStream = S.workletNode = S.audioCtx = null;
  S.micOn = false;
  $("btn-mic").className = "ctl";
  $("btn-mic").textContent = "🎙️ MIC";
  setStatus("HAZIR", true);
}

// ── Kamera ───────────────────────────────────────────────────────────────
async function startCam() {
  if (S.camOn) return;
  try {
    S.camStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, facingMode: "user" },
    });
  } catch {
    addLog("sys", "Kamera izni reddedildi.");
    return;
  }
  const video = $("cam");
  video.srcObject = S.camStream;
  $("cam-wrap").classList.remove("hidden");

  const canvas = document.createElement("canvas");
  const sendFrame = () => {
    if (!S.camOn || !S.ws || S.ws.readyState !== WebSocket.OPEN || !S.ready) return;
    const w = video.videoWidth, h = video.videoHeight;
    if (!w || !h) return;
    const scale = Math.min(1, 1024 / Math.max(w, h));
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    const ctx2 = canvas.getContext("2d");
    // Ayna — masaüstüyle aynı: AI ve kullanıcı aynı yönü görür
    ctx2.translate(canvas.width, 0);
    ctx2.scale(-1, 1);
    ctx2.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(async (blob) => {
      if (!blob) return;
      const buf = new Uint8Array(await blob.arrayBuffer());
      const out = new Uint8Array(1 + buf.length);
      out[0] = 0x02;
      out.set(buf, 1);
      if (S.ws && S.ws.readyState === WebSocket.OPEN) S.ws.send(out);
    }, "image/jpeg", 0.7);
  };

  S.camTimer = setInterval(sendFrame, 1500);
  S.camOn = true;
  $("btn-cam").className = "ctl rec";
  $("btn-cam").textContent = "🔴 CAM ON";
  addLog("sys", "Webcam CANLI");
}

function stopCam() {
  if (S.camTimer) clearInterval(S.camTimer);
  if (S.camStream) S.camStream.getTracks().forEach((t) => t.stop());
  S.camTimer = S.camStream = null;
  S.camOn = false;
  $("cam").srcObject = null;
  $("cam-wrap").classList.add("hidden");
  $("btn-cam").className = "ctl";
  $("btn-cam").textContent = "📷 CAM";
  addLog("sys", "Webcam KAPALI");
}

// ── Orb animasyonu ───────────────────────────────────────────────────────
const orbCanvas = $("orb");
const octx = orbCanvas.getContext("2d");
let tick = 0;

function drawOrb() {
  tick++;
  const dpr = window.devicePixelRatio || 1;
  const cssW = orbCanvas.clientWidth, cssH = orbCanvas.clientHeight;
  if (orbCanvas.width !== cssW * dpr) {
    orbCanvas.width = cssW * dpr;
    orbCanvas.height = cssH * dpr;
  }
  octx.setTransform(dpr, 0, 0, dpr, 0, 0);
  octx.clearRect(0, 0, cssW, cssH);

  const cx = cssW / 2, cy = cssH / 2;
  S.outLevel *= 0.92; // seviye sönümü

  const base = Math.min(cssW, cssH) * 0.30;
  const pulse = S.speaking
    ? 1 + 0.10 * Math.sin(tick * 0.25) + S.outLevel * 0.25
    : 1 + 0.02 * Math.sin(tick * 0.06);
  const r = base * pulse;

  // Dış halo
  const grad = octx.createRadialGradient(cx, cy, r * 0.2, cx, cy, r * 1.9);
  const glow = S.speaking ? 0.35 + S.outLevel * 0.3 : 0.18;
  grad.addColorStop(0, `rgba(0, 212, 196, ${glow})`);
  grad.addColorStop(1, "rgba(0, 212, 196, 0)");
  octx.fillStyle = grad;
  octx.beginPath();
  octx.arc(cx, cy, r * 1.9, 0, Math.PI * 2);
  octx.fill();

  // Çekirdek
  octx.strokeStyle = "rgba(0, 212, 196, 0.9)";
  octx.lineWidth = 2;
  octx.beginPath();
  octx.arc(cx, cy, r, 0, Math.PI * 2);
  octx.stroke();

  // Dönen yay segmentleri
  for (const [rr, speed, len] of [[1.25, 0.013, 1.4], [1.45, -0.009, 0.9]]) {
    const a0 = tick * speed;
    octx.strokeStyle = "rgba(0, 212, 196, 0.35)";
    octx.lineWidth = 1.5;
    octx.beginPath();
    octx.arc(cx, cy, r * rr, a0, a0 + len);
    octx.stroke();
    octx.beginPath();
    octx.arc(cx, cy, r * rr, a0 + Math.PI, a0 + Math.PI + len);
    octx.stroke();
  }

  // İç noktalar
  for (let i = 0; i < 5; i++) {
    const ang = tick * 0.02 + (i * Math.PI * 2) / 5;
    const dist = r * 0.55;
    octx.fillStyle = "rgba(0, 212, 196, 0.7)";
    octx.beginPath();
    octx.arc(cx + Math.cos(ang) * dist, cy + Math.sin(ang) * dist, 2, 0, Math.PI * 2);
    octx.fill();
  }

  requestAnimationFrame(drawOrb);
}

// ── UI olayları ──────────────────────────────────────────────────────────
$("btn-mic").addEventListener("click", () => (S.micOn ? stopMic() : startMic()));
$("btn-cam").addEventListener("click", () => (S.camOn ? stopCam() : startCam()));

$("text-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("text-input");
  const text = input.value.trim();
  if (!text || !S.ws || S.ws.readyState !== WebSocket.OPEN) return;
  S.ws.send(JSON.stringify({ type: "text", text }));
  addLog("user", text);
  input.value = "";
  ensurePlayCtx(); // kullanıcı jesti — ses çalma iznini garanti et
});

// ── API anahtarı ekranı (herkese açık mod) ───────────────────────────────
function showKeyScreen(errText) {
  S.awaitingKey = true;                       // reconnect'i durdur
  if (S.reconnectTimer) { clearTimeout(S.reconnectTimer); S.reconnectTimer = null; }
  const screen = $("key-screen");
  const input = $("key-input");
  screen.classList.remove("hidden");
  const note = screen.querySelector(".key-note");
  if (note) {
    note.textContent = errText
      ? "⚠️ " + errText
      : "Anahtarın yalnızca senin tarayıcında saklanır, sunucuda tutulmaz.";
  }
  setTimeout(() => input.focus(), 100);
}

function hideKeyScreen() {
  S.awaitingKey = false;
  $("key-screen").classList.add("hidden");
}

$("key-save").addEventListener("click", saveKeyAndStart);
$("key-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") saveKeyAndStart();
});

function saveKeyAndStart() {
  const key = $("key-input").value.trim();
  if (!key) return;
  S.apiKey = key;
  localStorage.setItem("jarvis_gemini_key", key);
  hideKeyScreen();
  ensurePlayCtx();          // kullanıcı jesti — iOS ses iznini garanti et
  S.reconnectDelay = 2000;
  S.fatalMsg = null;
  connect();
}

// ── Başlat ───────────────────────────────────────────────────────────────
async function initApp() {
  try {
    const info = await (await fetch("/mode")).json();
    S.public = !!info.public;
    // Sürüm damgası: "eski kurulumu mu açtım?" sorusunu ortadan kaldırır
    const stamp = $("build-stamp");
    if (stamp && info.build) stamp.textContent = info.build;
  } catch { S.public = false; }

  if (S.public) {
    S.apiKey = localStorage.getItem("jarvis_gemini_key") || "";
    if (!S.apiKey) {
      showKeyScreen();       // anahtar yok → giriş ekranı, kullanıcı girince connect
      return;
    }
  }
  connect();
}

initApp();
drawOrb();
