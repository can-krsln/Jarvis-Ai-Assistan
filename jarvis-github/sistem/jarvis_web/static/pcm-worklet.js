// Mikrofon PCM yakalayıcı — AudioWorklet
// Tarayıcı örnekleme hızından (44.1k/48k) 16 kHz mono Int16'ya çevirir
// ve ~64 ms'lik bloklar hâlinde ana iş parçacığına gönderir.

class PCMCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate;   // örn. 48000/16000 = 3
    this.readPos = 0;       // kaynak akışta kesirli okuma konumu
    this.prevTail = 0;      // bloklar arası interpolasyon için son örnek
    this.outBuf = new Int16Array(1024);          // 1024 örnek = 64 ms @16k
    this.outLen = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) return true;
    const src = input[0];

    // Doğrusal interpolasyonla yeniden örnekleme
    let pos = this.readPos;
    while (pos < src.length) {
      const i  = Math.floor(pos);
      const fr = pos - i;
      const s0 = i === 0 ? this.prevTail : src[i - 1];
      const s1 = src[i];
      const sample = s0 + (s1 - s0) * fr;

      let v = Math.max(-1, Math.min(1, sample));
      this.outBuf[this.outLen++] = v < 0 ? v * 0x8000 : v * 0x7FFF;

      if (this.outLen >= this.outBuf.length) {
        this.port.postMessage(this.outBuf.slice(0, this.outLen));
        this.outLen = 0;
      }
      pos += this.ratio;
    }
    this.readPos = pos - src.length;
    this.prevTail = src[src.length - 1];
    return true;
  }
}

registerProcessor('pcm-capture', PCMCaptureProcessor);
