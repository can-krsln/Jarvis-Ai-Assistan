"""JARVIS surum damgasi.

NEDEN VAR: Ayni makinede birden fazla kurulum olabiliyor (masaustu kisayolu,
indirilen paket, eski bir kopya). "Dogru dosyayi mi calistirdim?" sorusunu
tahmine birakmamak icin surum HEM arayuzde HEM telefon sayfasinda gorunur.
Kod her degistiginde BUILD guncellenir.
"""

VERSION = "3.2"
BUILD = "2026.10.18-1"

# Arayuzde/telefonda gosterilen tek satirlik damga
STAMP = f"v{VERSION} build {BUILD}"
