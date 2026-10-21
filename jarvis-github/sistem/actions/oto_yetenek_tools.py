"""OTO-YETENEK arac bildirimleri (telefon_tools.py duzeniyle ayni format).

Doktrin (modele baglayici): kullanici bir is istediginde ve hazir arac
yoksa "yapamam / yok / desteklenmiyor" DEME; yetenek_ekle ile eksik
yetenegi kendin kodla, kutuphaneye kaydet, yetenek_calistir ile calistir.
"""

S = lambda d: {'type': 'STRING', 'description': d}

OTO_YETENEK_TOOLS = [
    {'name': 'yetenek_ekle',
     'description': ('Eksik yetenegi KENDIN KODLA ve kutuphaneye ekle. '
                     'Kullanici bir is istediginde hazir arac yoksa "yapamam / yok / '
                     'desteklenmiyor" DEMEK YASAK: once bu aracla cozumu yaz. '
                     'kod, def calistir(...) icermeli ve sonucu str dondurmeli. '
                     'Elindeki araclari kodun icinden dogrudan cagiramazsin; '
                     'dis dunya isleri icin standart kutuphane (urllib, json, '
                     'pathlib, subprocess yerine shell_run ile yapilacaklari plana yaz) '
                     'kullan. Eklenen yetenek bu oturumda yetenek_calistir ile, '
                     'sonrakilerde dogrudan adiyla cagrilir.'),
     'parameters': {'type': 'OBJECT',
                    'properties': {
                        'ad': S('Yetenek adi: kucuk harf snake_case, 3-40 karakter. Orn: pdf_oku'),
                        'aciklama': S('Ne ise yarar, ne zaman kullanilir (1-2 cumle)'),
                        'kod': S("def calistir(...) iceren Python kodu"),
                        'parametreler': S('Opsiyonel JSON: {"param": "aciklama"}')},
                    'required': ['ad', 'aciklama', 'kod']}},
    {'name': 'yetenek_calistir',
     'description': ('Kutuphanedeki bir yetenegi calistir. Onceki adimda yetenek_ekle '
                     'ile ekledigin seyi bununla kostur.'),
     'parameters': {'type': 'OBJECT',
                    'properties': {
                        'ad': S('Yetenek adi'),
                        'argumanlar': S('Opsiyonel JSON: {"param": deger}')},
                    'required': ['ad']}},
    {'name': 'yetenek_listele',
     'description': ('Kutuphanedeki tum yetenekleri listele. Bir ise baslamadan once '
                     'buraya bak: belki daha once kendin eklemissindir, bastan yazma.'),
     'parameters': {'type': 'OBJECT', 'properties': {}, 'required': []}},
    {'name': 'yetenek_sil',
     'description': 'Kutuphaneden yetenek kaldir (bozuk/yanlis ekleneni temizle).',
     'parameters': {'type': 'OBJECT',
                    'properties': {'ad': S('Silinecek yetenek adi')},
                    'required': ['ad']}},
]
