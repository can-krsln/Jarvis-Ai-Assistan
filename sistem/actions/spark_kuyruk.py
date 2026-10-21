from __future__ import annotations
import json
import time
from pathlib import Path
from PIL import Image
BASE_DIR = Path(__file__).resolve().parent.parent
KUYRUK_DIR = BASE_DIR / 'kuyruk'
CEVAP_DIR = BASE_DIR / 'cevaplar'
def kuyruga_birak(query, image_path, owner_name='', window_title=''):
    KUYRUK_DIR.mkdir(parents=True, exist_ok=True)
    CEVAP_DIR.mkdir(parents=True, exist_ok=True)
    is_id = time.strftime('%Y%m%d-%H%M%S')
    img = Image.open(image_path).convert('RGB')
    img.thumbnail((1280, 1280))
    img.save(KUYRUK_DIR / (is_id + '.jpg'), 'JPEG', quality=72)
    meta = {'id': is_id, 'query': query, 'owner': owner_name, 'title': window_title, 'zaman': time.strftime('%d.%m %H:%M')}
    (KUYRUK_DIR / (is_id + '.json')).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return is_id
def spark_cevap_oku(is_id=''):
    if not is_id:
        txts = sorted(CEVAP_DIR.glob('*.txt')) if CEVAP_DIR.exists() else []
        if not txts:
            return 'Henuz cevap yazilmamis.'
        is_id = txts[-1].stem
    p = CEVAP_DIR / (is_id + '.txt')
    if not p.exists():
        return 'Bu is icin henuz cevap yazilmamis (' + is_id + ').'
    return p.read_text(encoding='utf-8')
