"""
Terminalde QR kod basar.

Ayri dosya olmasinin sebebi: bu kodu WEB_BASLAT.ps1 icine cok satirli bir
`python -c "..."` dizesi olarak gomdugumuzde PowerShell'in ayristiricisi
bozuluyordu. Betik dosyasi olarak cagirmak hem guvenli hem okunakli.

Kullanim:  python _show_qr.py <url>
"""

import sys


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        return 0
    url = sys.argv[1].strip()
    try:
        import qrcode
    except ImportError:
        # qrcode kurulu degilse sessizce gec — adres zaten ekranda yazili
        return 0

    try:
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make()
        print("   Telefon kamerasi ile bu QR kodu okut:")
        print()
        qr.print_ascii(invert=True)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
