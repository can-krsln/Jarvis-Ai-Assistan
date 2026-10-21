"""
Terminal komutu calistirma.

macOS   → bash
Windows → PowerShell
"""

import subprocess

from actions.platform_utils import IS_WIN, quiet_popen_kwargs


# Her platformda engellenen kaliplar
BLOCKED_COMMON = [
    "mkfs",
    "dd if=",
    ":(){:|:&};:",
    "shutdown",
    "reboot",
    "halt",
    ">:",
]

BLOCKED_MAC = [
    "rm -rf /",
    "sudo rm -rf",
    "diskutil erase",
    "diskutil apfs deletecontainer",
]

BLOCKED_WIN = [
    "format ",
    "diskpart",
    "bcdedit",
    "vssadmin delete",
    "cipher /w",
    "del /s",
    "rd /s",
    "rmdir /s",
    "remove-item -recurse",
    "clear-disk",
    "remove-partition",
    "restart-computer",
    "stop-computer",
    "set-executionpolicy",
    "reg delete",
    "sc delete",
]

# Dosya veya yetki degistiren komut baslangiclari
UNSAFE_PREFIXES_MAC = ("rm ", "mv ", "cp ", "chmod ", "chown ", "sudo ")
UNSAFE_PREFIXES_WIN = (
    "del ", "erase ", "rd ", "rmdir ", "move ", "ren ", "rename ",
    "icacls ", "takeown ", "attrib ", "runas ",
    "remove-item", "move-item", "rename-item", "set-acl",
)


def _blocked_patterns() -> list[str]:
    return BLOCKED_COMMON + (BLOCKED_WIN if IS_WIN else BLOCKED_MAC)


def _unsafe_prefixes() -> tuple[str, ...]:
    return UNSAFE_PREFIXES_WIN if IS_WIN else UNSAFE_PREFIXES_MAC


def shell_run(command: str, timeout: int = 30) -> str:
    if not command:
        return "Komut belirtilmedi."

    cmd_lower = command.lower()
    stripped_lower = command.strip().lower()

    pass  # TAM YETKI: kullanici tum komutlara izin verdi

    try:
        if IS_WIN:
            result = _run_windows(command, timeout)
        else:
            result = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=timeout
            )
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if not output:
            return "Komut basariyla calisti (cikti yok)."
        if len(output) > 800:
            output = output[:800] + "\n... (cikti kisaltildi)"
        return output
    except subprocess.TimeoutExpired:
        return f"Komut zaman asimina ugradi ({timeout}s)."
    except Exception as e:
        return f"Hata: {e}"


def _run_windows(command: str, timeout: int) -> subprocess.CompletedProcess:
    """Komutu PowerShell'de, gizli pencerede, UTF-8 ciktiyla calistirir."""
    wrapped = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + command
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", wrapped,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        **quiet_popen_kwargs(),
    )
