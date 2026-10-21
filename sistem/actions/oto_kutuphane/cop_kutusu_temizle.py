# cop_kutusu_temizle - oto-yetenek (JARVIS uretti)
# Windows cop kutusunu tamamen bosaltir. Kullanici cop kutusunu temizle ya da bosalt dediginde kullan.

def calistir():
    import subprocess
    def ps(komut, sure=60):
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", komut], capture_output=True, text=True, timeout=sure)
            return (r.stdout or "").strip()
        except Exception as e:
            return "CALISMA_HATASI:" + str(e)[:150]
    say = "((New-Object -ComObject Shell.Application).NameSpace(10).Items() | Measure-Object).Count"
    baslangic = ps(say) or "0"
    ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue")
    ps("(New-Object -ComObject Shell.Application).NameSpace(10).Items() | ForEach-Object { Remove-Item $_.Path -Recurse -Force -ErrorAction SilentlyContinue }", 120)
    kalan = ps(say) or "?"
    try:
        b, k = int(baslangic), int(kalan)
    except Exception:
        return "Cop kutusu temizleme denendi (sayim alinamadi)."
    if b == 0 and k == 0:
        return "Cop kutusu zaten bosti, yapilacak is yoktu."
    if k == 0:
        return "Cop kutusu temizlendi (%d dosya silindi)." % b
    return "Temizlemeden sonra %s dosya kaldi, bir kismi kilitli olabilir." % kalan

