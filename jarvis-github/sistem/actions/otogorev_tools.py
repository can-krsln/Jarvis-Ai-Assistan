S = lambda d: {'type': 'STRING', 'description': d}
OTOGOREV_TOOLS = [
    {'name': 'gorev_kur', 'description': 'OTOMATIK GOREV KURAR. Kullanici periyodik/surekli bir sey isterse ("her sabah", "her aksam", "saat basi", "duzenli", "her pazartesi") BUNU kullan, kendin takip etmeye CALISMA. Zaman ifadesini AYNEN gecir.', 'parameters': {'type': 'OBJECT', 'properties': {'talimat': S('Ne yapilacak (ornek: Sislide havayi soyle)'), 'zaman': S('Ne zaman (ornek: her sabah 08:00, her 30 dakikada, hafta ici 09:00)')}, 'required': ['talimat', 'zaman']}},
    {'name': 'gorev_listele', 'description': 'Kurulu otomatik gorevleri listeler. Kullanici "gorevlerim ne / neler kurdun" derse kullan.', 'parameters': {'type': 'OBJECT', 'properties': {}, 'required': []}},
    {'name': 'gorev_sil', 'description': 'Otomatik gorevi iptal eder/siler. Numara (#3) ya da talimattan bir parca verilir.', 'parameters': {'type': 'OBJECT', 'properties': {'hedef': S('Gorev numarasi ya da adi')}, 'required': ['hedef']}},
    {'name': 'gorev_sonuclari', 'description': 'Calisan otomatik gorevlerin SONUCLARINI okur. Kullanici "dun gece ne yaptin / gorevler ne yapti" derse kullan.', 'parameters': {'type': 'OBJECT', 'properties': {'sayi': S('Kac sonuc (varsayilan 5)')}, 'required': []}},
]
