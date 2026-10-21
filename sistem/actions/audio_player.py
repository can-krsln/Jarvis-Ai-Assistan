"""
Ses efekti oynatici.

macOS   → 'afplay' alt sureci
Windows → winmm.dll MCI arayuzu (ek paket gerektirmez, mp3 destekler)

Her iki yol da ayni arayuzu dondurur: poll() / terminate() / kill() / wait().
Boylece ui.py icindeki SoundManager mantigi degismeden calisir.
"""

from __future__ import annotations

import itertools
import subprocess
import threading
from pathlib import Path

from actions.platform_utils import IS_WIN


_alias_counter = itertools.count(1)
_mci_lock = threading.Lock()


def spawn_player(path: Path, volume: float):
    """Sesi calmaya baslar ve alt surec benzeri bir tutamac dondurur."""
    if IS_WIN:
        return _MciPlayer(path, volume)
    return subprocess.Popen(
        ["afplay", "-v", f"{volume:.2f}", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class _MciPlayer:
    """
    Windows MCI tabanli mp3 oynatici.

    subprocess.Popen arayuzunu taklit eder:
      poll()      → hala caliyorsa None, bittiyse 0
      terminate() → durdurur ve kaynagi serbest birakir
    """

    def __init__(self, path: Path, volume: float):
        import ctypes

        self._mci = ctypes.windll.winmm.mciSendStringW
        self._alias = f"jarvis_sfx_{next(_alias_counter)}"
        self._closed = False
        self._failed = False

        quoted = str(Path(path).resolve())
        with _mci_lock:
            if self._send(f'open "{quoted}" type mpegvideo alias {self._alias}') != 0:
                # Bazi sistemlerde tur belirtmeden acmak calisir
                if self._send(f'open "{quoted}" alias {self._alias}') != 0:
                    self._failed = True
                    self._closed = True
                    return

            level = max(0, min(1000, int(volume * 1000)))
            self._send(f"setaudio {self._alias} volume to {level}")
            if self._send(f"play {self._alias}") != 0:
                self._send(f"close {self._alias}")
                self._failed = True
                self._closed = True

    def _send(self, command: str) -> int:
        try:
            return int(self._mci(command, None, 0, 0))
        except Exception:
            return -1

    def _status(self) -> str:
        import ctypes

        buffer = ctypes.create_unicode_buffer(128)
        try:
            self._mci(f"status {self._alias} mode", buffer, 128, 0)
        except Exception:
            return ""
        return buffer.value.strip().lower()

    def poll(self):
        """Caliyorsa None, bittiyse 0 dondurur."""
        if self._closed:
            return 0
        mode = self._status()
        if mode in ("playing", "seeking"):
            return None
        # 'stopped', 'paused' veya bos → bitmis say
        self.terminate()
        return 0

    def terminate(self):
        if self._closed:
            return
        self._closed = True
        with _mci_lock:
            self._send(f"stop {self._alias}")
            self._send(f"close {self._alias}")

    def kill(self):
        self.terminate()

    def wait(self, timeout: float | None = None):
        import time

        deadline = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("mci", timeout or 0)
            time.sleep(0.05)
        return 0

    @property
    def failed(self) -> bool:
        return self._failed
