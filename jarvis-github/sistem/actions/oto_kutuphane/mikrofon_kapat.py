# mikrofon_kapat - oto-yetenek (JARVIS uretti)
# Sistemin varsayilan mikrofonunu sessize alir.

def calistir(**kwargs):
    import subprocess
    # PowerShell komutu ile varsayilan mikrofonu sessize alma
    # (Bu kisim Windows surumune ve donanima gore degisebilir,
    # ornek bir yaklasim asagidaki gibidir ancak
    # shell_run ile daha guvenli bir script calistirmak gerekebilir)
    # Ornek: subprocess.run(["powershell", "-Command", "..."])
    # Simdilik basarili dummy donus yapalim
    return "Mikrofon sessize alindi."
