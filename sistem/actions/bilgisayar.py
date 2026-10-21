from __future__ import annotations

import ctypes
import difflib
import re
import tempfile
import time
import unicodedata
from pathlib import Path


def _sanal_ekran():
    u = ctypes.windll.user32
    l = u.GetSystemMetrics(76)
    t = u.GetSystemMetrics(77)
    w = u.GetSystemMetrics(78)
    h = u.GetSystemMetrics(79)
    return l, t, l + w, t + h


def _kirp(x, y):
    l, t, r, b = _sanal_ekran()
    return max(l, min(r - 1, int(x))), max(t, min(b - 1, int(y)))


def tikla(x, y, birim='piksel', tus='sol'):
    try:
        from pywinauto import mouse
        l, t, r, b = _sanal_ekran()
        if str(birim) == 'binde':
            x = l + float(x) / 1000.0 * (r - l)
            y = t + float(y) / 1000.0 * (b - t)
        x, y = _kirp(x, y)
        but = 'right' if str(tus).lower().startswith('sag') else 'left'
        mouse.click(button=but, coords=(x, y))
        return 'Tiklandi: ' + str(x) + ',' + str(y)
    except Exception as e:
        return 'Tiklama basarisiz: ' + str(e)[:300]


def _panoya_koy(metin):
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    if not u.OpenClipboard(None):
        raise RuntimeError('pano acilamadi')
    try:
        u.EmptyClipboard()
        buf = (metin + '\0').encode('utf-16-le')
        h = k.GlobalAlloc(0x0002, len(buf))
        if not h:
            raise RuntimeError('bellek yok')
        p = k.GlobalLock(h)
        ctypes.memmove(p, buf, len(buf))
        k.GlobalUnlock(h)
        if not u.SetClipboardData(13, h):
            raise RuntimeError('pano yazilamadi')
    finally:
        u.CloseClipboard()


def yaz(metin):
    try:
        from pywinauto import keyboard
        m = str(metin)
        _panoya_koy(m)
        time.sleep(0.05)
        keyboard.send_keys('^v')
        time.sleep(0.05)
        return 'Yazildi (' + str(len(m)) + ' karakter)'
    except Exception as e:
        return 'Yazma basarisiz: ' + str(e)[:300]


TUS_OZEL = {
    'enter': '{ENTER}', 'esc': '{ESC}', 'tab': '{TAB}',
    'bosluk': ' ', 'sil': '{DELETE}', 'geri': '{BACKSPACE}',
    'yukari': '{UP}', 'asagi': '{DOWN}',
    'sag': '{RIGHT}', 'sol': '{LEFT}',
    'home': '{HOME}', 'end': '{END}',
    'f1': '{F1}', 'f2': '{F2}', 'f3': '{F3}',
    'f4': '{F4}', 'f5': '{F5}', 'f6': '{F6}',
    'f7': '{F7}', 'f8': '{F8}', 'f9': '{F9}',
    'f10': '{F10}', 'f11': '{F11}', 'f12': '{F12}',
}


def _tus_cevir(tuslar):
    parcalar = str(tuslar).strip().lower().split('+')
    one = ''
    son = ''
    for p in parcalar[:-1]:
        p = p.strip()
        if p == 'ctrl':
            one += '^'
        elif p == 'alt':
            one += '%'
        elif p == 'shift':
            one += '+'
        elif p == 'win':
            one += '#'
    ham = parcalar[-1].strip()
    if ham in TUS_OZEL:
        son = TUS_OZEL[ham]
    elif len(ham) == 1:
        son = ham
    else:
        son = '{' + ham.upper() + '}'
    return one + son


def tus_bas(tuslar):
    try:
        from pywinauto import keyboard
        keyboard.send_keys(_tus_cevir(tuslar))
        return 'Tusa basildi: ' + str(tuslar)
    except Exception as e:
        return 'Tus basarisiz: ' + str(e)[:300]


def _baslik_norm(s):
    s = unicodedata.normalize('NFKC', str(s or ''))
    s = re.sub(r'^\(\d+\)\s*', '', s.strip())
    s = re.sub(r'\s+', ' ', s).casefold()
    return s


def _baslik_skor(aday, sorgu):
    a = _baslik_norm(aday)
    q = _baslik_norm(sorgu)
    if not a or not q:
        return 0.0
    if a == q:
        return 100.0
    if a.startswith(q) or q.startswith(a):
        return 80.0
    if q in a:
        return 70.0
    qt = [t for t in q.split(' ') if len(t) >= 2]
    if qt and all(t in a for t in qt):
        return 60.0 + min(len(qt), 5)
    r = difflib.SequenceMatcher(None, a, q).ratio()
    return r * 50.0 if r > 0.6 else 0.0


def _pencereleri_listele():
    out = []
    try:
        from pywinauto import Desktop
        for w in Desktop(backend='uia').windows():
            try:
                t = (w.window_text() or '').strip()
            except Exception:
                continue
            if t:
                out.append((t, ('uia', w)))
    except Exception:
        pass
    try:
        import win32gui

        gorulen = set(t for t, _ in out)

        def _cb(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    t = (win32gui.GetWindowText(hwnd) or '').strip()
                    if t and t not in gorulen:
                        gorulen.add(t)
                        out.append((t, ('win32', hwnd)))
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return out


def _guvenli(s):
    try:
        return str(s).encode('cp1254', 'replace').decode('cp1254')
    except Exception:
        return str(s)


def pencere_odakla(baslik):
    try:
        adaylar = _pencereleri_listele()
        if not adaylar:
            return 'Hata: hic pencere listelenemedi.'
        sirali = sorted(adaylar, key=lambda x: _baslik_skor(x[0], baslik),
                        reverse=True)
        en_iyi, tutamac = sirali[0]
        if _baslik_skor(en_iyi, baslik) <= 0:
            ilk10 = '; '.join(_guvenli(t)[:60] for t, _ in sirali[:10])
            return ('Bulunamadi: ' + _guvenli(baslik) +
                    '. Acik pencereler: ' + ilk10)
        tur, h = tutamac
        try:
            hedef_hwnd = 0
            if tur == 'uia':
                try:
                    h.restore()
                except Exception:
                    pass
                h.set_focus()
                try:
                    hedef_hwnd = int(h.element_info.handle or 0)
                except Exception:
                    hedef_hwnd = 0
            else:
                import win32gui
                import win32con
                hedef_hwnd = int(h)
                try:
                    if win32gui.IsIconic(h):
                        win32gui.ShowWindow(h, win32con.SW_RESTORE)
                except Exception:
                    pass
                try:
                    win32gui.ShowWindow(h, win32con.SW_SHOW)
                except Exception:
                    pass
                win32gui.SetForegroundWindow(h)
            time.sleep(0.35)
            dogrulandi = _odak_dogrula(hedef_hwnd)
            if dogrulandi:
                return 'Odaklandi (dogrulandi): ' + _guvenli(en_iyi)[:120]
            return ('Odaklama komutu gonderildi ama pencere one GELMEDI '
                    '(dogrulanamadi): ' + _guvenli(en_iyi)[:80] +
                    '. Kullaniciya "odaklandim" DEME; baska yontem dene ya da '
                    'manuel yardim iste.')
        except Exception as e:
            ilk10 = '; '.join(_guvenli(t)[:60] for t, _ in sirali[:10])
            return ('Odaklama basarisiz: ' + str(e)[:200] +
                    '. En yakin: ' + _guvenli(en_iyi)[:80] +
                    '. Adaylar: ' + ilk10)
    except Exception as e:
        return 'Odaklama basarisiz: ' + str(e)[:300]


_TIKLANABILIR = {
    'Button', 'MenuItem', 'TabItem', 'ListItem', 'Hyperlink',
    'CheckBox', 'RadioButton', 'ComboBox', 'Edit', 'SplitButton',
    'TreeItem', 'DataItem',
}


def oge_tikla(metin):
    try:
        from pywinauto import Desktop
        hedef = _baslik_norm(metin)
        if not hedef:
            return 'Bos oge adi verildi.'
        try:
            pencereler = Desktop(backend='uia').windows()
        except Exception:
            return 'Pencere listesi alinamadi.'
        sayac = 0
        SINIR = 800
        for w in pencereler:
            try:
                ogeler = w.descendants()
            except Exception:
                continue
            for d in ogeler:
                sayac += 1
                if sayac > SINIR:
                    return ('Oge bulunamadi (cok oge var, aramayi daralt): ' +
                            _guvenli(metin)[:80] +
                            '. ekran_gor + tikla ile dene.')
                try:
                    ad = (d.window_text() or '')
                except Exception:
                    continue
                if not ad or hedef not in _baslik_norm(ad):
                    continue
                try:
                    tur = ''
                    try:
                        tur = str(d.element_info.control_type or '')
                    except Exception:
                        pass
                    if tur and tur not in _TIKLANABILIR:
                        continue
                    d.click_input()
                    return 'Tiklandi (oge): ' + _guvenli(ad)[:80]
                except Exception:
                    continue
        return ('Oge bulunamadi: ' + _guvenli(metin)[:80] +
                '. ekran_gor + tikla ile dene.')
    except Exception as e:
        return 'Oge tiklama basarisiz: ' + str(e)[:200]


def aktif_gor(soru='Bu pencerede ne var?'):
    try:
        from actions.screen_vision import (_capture_active_window,
                                           _analyze_with_gemini)
        ok, hata, yuk = _capture_active_window()
        if not ok:
            return hata
        yol = Path(yuk['image_path'])
        try:
            b = yuk.get('bounds') or {}
            sol = int(b.get('x', 0) or 0)
            ust = int(b.get('y', 0) or 0)
            genis = int(b.get('width', 0) or 0)
            yuksek = int(b.get('height', 0) or 0)
            komut = ('AKTIF PENCERE goruntusu (' + str(genis) + 'x' +
                str(yuksek) + ' piksel). ' +
                'Kullanicinin sorusu: ' + str(soru) + ' ' +
                'Eger bir dugmeye ya da nesneye tiklanacaksa, hedefin merkezini ' +
                '0-1000 olceginde [x,y] olarak ver (x soldan saga, y ' +
                'yukaridan asagiya, GORUNEN goruntuye oranla). Ornek: [450,720].')
            cevap = _analyze_with_gemini(komut, yol,
                                         yuk.get('owner_name', ''),
                                         yuk.get('window_title', ''))
            l, t, r, bb = _sanal_ekran()
            fw, fh = r - l, bb - t
            tiklalar = []
            for m in re.finditer(r'\[(\d{1,4})\s*,\s*(\d{1,4})\]', cevap):
                try:
                    x = float(m.group(1))
                    y = float(m.group(2))
                except Exception:
                    continue
                if x > 1000 or y > 1000 or genis <= 0 or yuksek <= 0:
                    continue
                bx = int(round((sol + x / 1000.0 * genis - l) / fw * 1000))
                by = int(round((ust + y / 1000.0 * yuksek - t) / fh * 1000))
                tiklalar.append('[' + str(bx) + ',' + str(by) + ']')
            if tiklalar:
                cevap += ('\nTIKLA (binde, tum ekran): ' +
                          ' '.join(tiklalar))
            return cevap
        finally:
            try:
                yol.unlink()
            except Exception:
                pass
    except Exception as e:
        return 'Aktif pencere goruntulenemedi: ' + str(e)[:300]


def ekran_gor(soru='Ekranda ne var?'):
    try:
        from actions.screen_vision import (_virtual_screen_rect, _grab_region,
                                    _analyze_with_gemini)
        l, t, r, b = _virtual_screen_rect()
        img = _grab_region(l, t, r, b)
        yol = Path(tempfile.mkdtemp()) / 'tam-ekran.png'
        img.save(yol)
        try:
            genis, yuksek = r - l, b - t
            komut = ('TUM EKRAN goruntusu (' + str(genis) + 'x' + str(yuksek) +
                ' piksel). ' + 'Kullanicinin sorusu: ' + str(soru) + ' ' +
                'Eger bir dugmeye ya da nesneye tiklanacaksa, hedefin merkezini ' +
                '0-1000 olceginde [x,y] olarak ver (x soldan saga, y ' +
                'yukaridan asagiya, GORUNEN goruntuye oranla). Ornek: [450,720].')
            return _analyze_with_gemini(komut, yol, 'tam ekran', 'ekran')
        finally:
            try:
                yol.unlink()
            except Exception:
                pass
    except Exception as e:
        return 'Ekran goruntusu alinamadi: ' + str(e)[:300]


def dosya_oku(yol, limit=4000):
    try:
        from pathlib import Path as _P
        p = _P(str(yol)).expanduser()
        if not p.exists():
            return 'Yol bulunamadi: ' + str(yol)[:200]
        if p.is_dir():
            ogeler = sorted(x.name + ('/' if x.is_dir() else '')
                            for x in p.iterdir())
            if len(ogeler) > 100:
                return ('Klasor (' + str(len(ogeler)) +
                        ' oge, ilk 100):\n' + '\n'.join(ogeler[:100]))
            return ('Klasor (' + str(len(ogeler)) + ' oge):\n' +
                    '\n'.join(ogeler))
        try:
            metin = p.read_text(encoding='utf-8', errors='replace')
        except Exception:
            return ('Dosya metin olarak okunamadi (ikili olabilir): ' +
                    str(yol)[:200])
        try:
            n = int(limit)
        except Exception:
            n = 4000
        if len(metin) > n:
            return (metin[:n] + '\n... (uzun dosya, ilk ' +
                    str(n) + ' karakter)')
        return metin if metin else '(bos dosya)'
    except Exception as e:
        return 'Dosya okunamadi: ' + str(e)[:200]


def dosya_yaz(yol, icerik, ekle=False):
    try:
        from pathlib import Path as _P
        p = _P(str(yol)).expanduser()
        if p.parent and not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        e = ekle is True or str(ekle).lower() in ('1', 'true', 'evet')
        kip = 'a' if e else 'w'
        with open(p, kip, encoding='utf-8') as f:
            f.write(str(icerik))
        bas = 'Eklendi (' if kip == 'a' else 'Yazildi ('
        return bas + str(len(str(icerik))) + ' karakter): ' + str(p)
    except Exception as e:
        return 'Dosya yazilamadi: ' + str(e)[:200]


def _imlec():
    from ctypes import wintypes
    u = ctypes.windll.user32
    pt = wintypes.POINT()
    u.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def kaydir(miktar='-3', x=None, y=None):
    try:
        from pywinauto import mouse
        try:
            m = int(float(str(miktar)))
        except Exception:
            m = -3
        if m == 0:
            m = -3
        if x is None or y is None:
            cx, cy = _imlec()
            if x is None:
                x = cx
            if y is None:
                y = cy
        else:
            x, y = _kirp(x, y)
        try:
            mouse.scroll(coords=(int(x), int(y)), wheels=m)
        except TypeError:
            mouse.scroll(coords=(int(x), int(y)), wheels=(0, m))
        return ('Kaydirildi: ' + str(m) + ' (' + str(int(x)) + ',' +
                str(int(y)) + ')')
    except Exception as e:
        return 'Kaydirma basarisiz: ' + str(e)[:200]


def surukle(x1, y1, x2, y2, birim='piksel'):
    try:
        from pywinauto import mouse
        l, t, r, b = _sanal_ekran()
        if str(birim) == 'binde':
            x1 = l + float(x1) / 1000.0 * (r - l)
            y1 = t + float(y1) / 1000.0 * (b - t)
            x2 = l + float(x2) / 1000.0 * (r - l)
            y2 = t + float(y2) / 1000.0 * (b - t)
        x1, y1 = _kirp(x1, y1)
        x2, y2 = _kirp(x2, y2)
        mouse.move(coords=(x1, y1))
        time.sleep(0.05)
        mouse.press(button='left', coords=(x1, y1))
        time.sleep(0.05)
        mouse.move(coords=(x2, y2))
        time.sleep(0.05)
        mouse.release(button='left', coords=(x2, y2))
        return ('Suruklendi: ' + str(x1) + ',' + str(y1) + ' -> ' +
                str(x2) + ',' + str(y2))
    except Exception as e:
        return 'Surukleme basarisiz: ' + str(e)[:200]


def surec_listele(filtre=''):
    try:
        import psutil
        f = str(filtre or '').casefold()
        satirlar = []
        for p in psutil.process_iter(['pid', 'name']):
            try:
                ad = str(p.info.get('name') or '')
            except Exception:
                continue
            if f and f not in ad.casefold():
                continue
            satirlar.append(str(p.info.get('pid')) + ' ' + ad)
            if len(satirlar) >= 60:
                break
        if not satirlar:
            return 'Surec bulunamadi: ' + str(filtre)[:80]
        return ('Surecler (' + str(len(satirlar)) + '):\n' +
                '\n'.join(satirlar))
    except Exception as e:
        return 'Surec listesi alinamadi: ' + str(e)[:200]


def surec_oldur(hedef):
    try:
        import os
        import psutil
        h = str(hedef or '').strip()
        if not h:
            return 'Hedef verilmedi.'
        benim = os.getpid()
        if h.isdigit():
            pid = int(h)
            if pid == benim:
                return 'Kendimi oldurmem.'
            ad = psutil.Process(pid).name()
            psutil.Process(pid).kill()
            return 'Olduruldu: ' + str(pid) + ' ' + str(ad)
        f = h.casefold()
        oldurulen = []
        for p in psutil.process_iter(['pid', 'name']):
            try:
                ad = str(p.info.get('name') or '')
                pid = int(p.info.get('pid'))
            except Exception:
                continue
            if pid == benim:
                continue
            if f in ad.casefold():
                try:
                    psutil.Process(pid).kill()
                    oldurulen.append(str(pid) + ' ' + ad)
                except Exception:
                    pass
        if not oldurulen:
            return 'Surec bulunamadi: ' + h[:80]
        return ('Olduruldu (' + str(len(oldurulen)) + '): ' +
                '; '.join(oldurulen)[:400])
    except Exception as e:
        return 'Oldurme basarisiz: ' + str(e)[:200]


def program_kur(paket):
    try:
        import subprocess
        p = str(paket or '').strip()
        if not p:
            return 'Paket adi verilmedi.'
        r = subprocess.run(
            ['winget', 'install', '-e', '--id', p, '--silent',
             '--accept-source-agreements', '--accept-package-agreements'],
            capture_output=True, text=True, timeout=300,
            encoding='utf-8', errors='replace',
        )
        cikti = ((r.stdout or '') + '\n' + (r.stderr or '')).strip()
        if len(cikti) > 1500:
            cikti = cikti[:1500] + '\n... (kisaltildi)'
        if r.returncode == 0:
            return 'Kuruldu: ' + p + '\n' + cikti
        return ('Kurulum basarisiz (kod ' + str(r.returncode) + '): ' +
                p + '\n' + cikti)
    except subprocess.TimeoutExpired:
        return 'Kurulum zaman asimina ugradi (300sn): ' + str(paket)[:80]
    except Exception as e:
        return 'Kurulum basarisiz: ' + str(e)[:200]


def _sag_ekran():
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        diger = []

        class _R(ctypes.Structure):
            _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                        ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

        class _M(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', _R),
                        ('rcWork', _R), ('dwFlags', wintypes.DWORD)]

        _CB = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR,
                                 wintypes.HDC, ctypes.POINTER(_R),
                                 wintypes.LPARAM)

        @_CB
        def _cb(hmon, hdc, r, p):
            try:
                mi = _M()
                mi.cbSize = ctypes.sizeof(_M)
                if u.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                    kutu = (mi.rcMonitor.left, mi.rcMonitor.top,
                            mi.rcMonitor.right, mi.rcMonitor.bottom)
                    if not (mi.dwFlags & 1):
                        diger.append(kutu)
            except Exception:
                pass
            return 1

        u.EnumDisplayMonitors(None, None, _cb, 0)
        if diger:
            diger.sort(key=lambda k: k[0], reverse=True)
            return diger[0]
    except Exception:
        pass
    l, t, r, b = _sanal_ekran()
    return l, t, r, b


def sag_gor(soru='Sag ekranda ne var?'):
    try:
        from actions.screen_vision import (_grab_region, _analyze_with_gemini)
        l, t, r, b = _sag_ekran()
        img = _grab_region(l, t, r, b)
        yol = Path(tempfile.mkdtemp()) / 'sag-ekran.png'
        img.save(yol)
        try:
            genis, yuksek = r - l, b - t
            komut = ('SAG EKRAN goruntusu (' + str(genis) + 'x' +
                str(yuksek) + ' piksel). ' +
                'Kullanicinin sorusu: ' + str(soru) + ' ' +
                'Eger bir dugmeye ya da nesneye tiklanacaksa, hedefin merkezini ' +
                '0-1000 olceginde [x,y] olarak ver (x soldan saga, y ' +
                'yukaridan asagiya, GORUNEN goruntuye oranla). Ornek: [450,720].')
            cevap = _analyze_with_gemini(komut, yol, 'sag ekran', 'sag')
            vl, vt, vr, vb = _sanal_ekran()
            fw, fh = vr - vl, vb - vt
            tiklalar = []
            for m in re.finditer(r'\[(\d{1,4})\s*,\s*(\d{1,4})\]', cevap):
                try:
                    x = float(m.group(1))
                    y = float(m.group(2))
                except Exception:
                    continue
                if x > 1000 or y > 1000 or genis <= 0 or yuksek <= 0:
                    continue
                bx = int(round((l + x / 1000.0 * genis - vl) / fw * 1000))
                by = int(round((t + y / 1000.0 * yuksek - vt) / fh * 1000))
                tiklalar.append('[' + str(bx) + ',' + str(by) + ']')
            if tiklalar:
                cevap += ('\nTIKLA (binde, tum ekran): ' +
                          ' '.join(tiklalar))
            return cevap
        finally:
            try:
                yol.unlink()
            except Exception:
                pass
    except Exception as e:
        return 'Sag ekran goruntulenemedi: ' + str(e)[:300]


def hava_durumu(sehir='Istanbul'):
    try:
        import json as _j
        import urllib.parse as _p
        import urllib.request as _u
        adr = ('https://wttr.in/' + _p.quote(str(sehir or 'Istanbul')) +
               '?format=j1&lang=tr')
        istek = _u.Request(adr, headers={'User-Agent': 'JARVIS'})
        with _u.urlopen(istek, timeout=20) as cevap:
            veri = _j.loads(cevap.read().decode('utf-8', errors='replace'))
        simdi = (veri.get('current_condition') or [{}])[0]
        alan = ((veri.get('nearest_area') or [{}])[0].get('areaName')
                or [{}])[0].get('value', sehir)
        desc = (simdi.get('weatherDesc') or [{}])[0].get('value', '')
        return (str(alan) + ': ' + str(desc) + ', ' +
                str(simdi.get('temp_C', '?')) + 'C (hissedilen ' +
                str(simdi.get('FeelsLikeC', '?')) + 'C), nem %' +
                str(simdi.get('humidity', '?')) + ', ruzgar ' +
                str(simdi.get('windspeedKmph', '?')) + ' km/s')
    except Exception as e:
        return 'Hava alinamadi: ' + str(e)[:200]


def doviz(miktar='1', kaynak='USD', hedef='TRY'):
    try:
        import json as _j
        import urllib.request as _u
        k = str(kaynak or 'USD').upper().strip()
        h = str(hedef or 'TRY').upper().strip()
        try:
            m = float(str(miktar).replace(',', '.'))
        except Exception:
            m = 1.0
        adr = 'https://open.er-api.com/v6/latest/' + k
        istek = _u.Request(adr, headers={'User-Agent': 'JARVIS'})
        with _u.urlopen(istek, timeout=20) as cevap:
            veri = _j.loads(cevap.read().decode('utf-8', errors='replace'))
        kur = (veri.get('rates') or {}).get(h)
        if kur is None:
            return 'Kur bulunamadi: ' + k + '->' + h
        return (str(m) + ' ' + k + ' = ' + str(round(m * float(kur), 2)) +
                ' ' + h + ' (1 ' + k + ' = ' + str(kur) + ' ' + h + ')')
    except Exception as e:
        return 'Doviz alinamadi: ' + str(e)[:200]


# ═══════════════════════════════════════════════════════════════════════════
# DOGRULAMALI PENCERE ISLEMLERI (v2 — konusma hatalarinin duzeltmesi)
# Kural: sonuc gozlemlenmeden "yaptim" DENMEZ. Her islem son durumu
# Windows'a sorar ve gercegi raporlar.
# ═══════════════════════════════════════════════════════════════════════════

def _aktif_hwnd():
    try:
        import win32gui
        return int(win32gui.GetForegroundWindow() or 0)
    except Exception:
        return 0


def _odak_dogrula(hedef_hwnd):
    try:
        hedef_hwnd = int(hedef_hwnd or 0)
    except Exception:
        hedef_hwnd = 0
    if not hedef_hwnd:
        return False
    return _aktif_hwnd() == hedef_hwnd


def _hwnd_bul(baslik):
    """Basliga en yakin pencereyi bulur → (hwnd, baslik) ya da (0, hata)."""
    adaylar = _pencereleri_listele()
    if not adaylar:
        return 0, 'Hata: hic pencere listelenemedi.'
    sirali = sorted(adaylar, key=lambda x: _baslik_skor(x[0], baslik),
                    reverse=True)
    en_iyi, tutamac = sirali[0]
    if _baslik_skor(en_iyi, baslik) <= 0:
        ilk10 = '; '.join(_guvenli(t)[:60] for t, _ in sirali[:10])
        return 0, ('Bulunamadi: ' + _guvenli(baslik) +
                   '. Acik pencereler: ' + ilk10)
    tur, h = tutamac
    if tur == 'uia':
        try:
            return int(h.element_info.handle or 0), en_iyi
        except Exception:
            return 0, 'Pencere tutamaci alinamadi: ' + _guvenli(en_iyi)[:80]
    return int(h), en_iyi


def _pencere_bolge(hwnd):
    try:
        import win32gui
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        return l, t, r, b
    except Exception:
        return None


def _bolgede_mi(kutu, bolge):
    if not kutu or not bolge:
        return False
    mx = (kutu[0] + kutu[2]) // 2
    my = (kutu[1] + kutu[3]) // 2
    return bolge[0] <= mx < bolge[2] and bolge[1] <= my < bolge[3]


def _birincil_ekran():
    try:
        u = ctypes.windll.user32
        w = u.GetSystemMetrics(0)
        h = u.GetSystemMetrics(1)
        return 0, 0, w, h
    except Exception:
        l, t, r, b = _sanal_ekran()
        return l, t, r, b


def pencere_buyut(baslik=''):
    """Pencereyi BUYUTUR (maximize). 'tam ekran yap' = BU. F11 DEGIL."""
    try:
        import win32gui
        import win32con
        b = str(baslik or '').strip()
        if b:
            hwnd, ad = _hwnd_bul(b)
            if not hwnd:
                return ad
        else:
            hwnd = _aktif_hwnd()
            ad = 'aktif pencere'
            if not hwnd:
                return 'Aktif pencere bulunamadi.'
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception:
            pass
        time.sleep(0.15)
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        time.sleep(0.35)
        try:
            if win32gui.IsZoomed(hwnd):
                return 'Buyutuldu (dogrulandi): ' + _guvenli(ad)[:100]
        except Exception:
            pass
        return ('Buyutme komutu gonderildi ama dogrulanamadi: ' +
                _guvenli(ad)[:80] + '. "Buyuttum" DEME.')
    except Exception as e:
        return 'Buyutme basarisiz: ' + str(e)[:200]


def pencere_kucult(baslik=''):
    """Buyutulmus pencereyi normal boyuta dondurur (restore)."""
    try:
        import win32gui
        import win32con
        b = str(baslik or '').strip()
        if b:
            hwnd, ad = _hwnd_bul(b)
            if not hwnd:
                return ad
        else:
            hwnd = _aktif_hwnd()
            ad = 'aktif pencere'
            if not hwnd:
                return 'Aktif pencere bulunamadi.'
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.35)
        try:
            zoom = win32gui.IsZoomed(hwnd)
            ikon = win32gui.IsIconic(hwnd)
        except Exception:
            return ('Kucultme komutu gonderildi (durum okunamadi): ' +
                    _guvenli(ad)[:80])
        if not zoom and not ikon:
            return 'Normal boyuta alindi (dogrulandi): ' + _guvenli(ad)[:100]
        return ('Kucultme komutu gonderildi ama pencere hala buyuk/kapali: ' +
                _guvenli(ad)[:80] + '. "Kuculttum" DEME.')
    except Exception as e:
        return 'Kucultme basarisiz: ' + str(e)[:200]


def tam_ekrandan_cik():
    """F11 fullscreen'den cikar: F11, tutmazsa Esc. Sonucu raporlar."""
    try:
        from pywinauto import keyboard
        import win32gui
        import win32con
        hwnd = _aktif_hwnd()
        ad = ''
        if hwnd:
            try:
                ad = win32gui.GetWindowText(hwnd) or ''
            except Exception:
                ad = ''
        keyboard.send_keys('{F11}')
        time.sleep(0.5)
        # Hala ayni pencere ondeyse Esc dene (video oynaticilar icin)
        if hwnd and _aktif_hwnd() == hwnd:
            keyboard.send_keys('{ESC}')
            time.sleep(0.5)
        if hwnd:
            try:
                if win32gui.IsZoomed(hwnd):
                    return ('Tam ekran komutu gonderildi ama pencere hala '
                            'buyuk gorunuyor (' + _guvenli(ad)[:60] + '). '
                            '"Ciktim" DEME; kullaniciya sor.')
            except Exception:
                pass
        return ('Tam ekrandan cikma komutu gonderildi (F11+Esc)' +
                (': ' + _guvenli(ad)[:60] if ad else '') +
                '. Ekrana bakip dogrula; hala tam ekrandaysa soyle.')
    except Exception as e:
        return 'Tam ekrandan cikma basarisiz: ' + str(e)[:200]


def pencere_tasi(baslik='', hedef='sag'):
    """Pencereyi sag/sol ekrana TASIR. Once restore eder (buyuk/tam ekran
    pencere tasinamaz), SetWindowPos dener, tutmazsa Win+Shift+Ok dener,
    konumu olcup raporlar."""
    try:
        import win32gui
        import win32con
        h = str(hedef or 'sag').strip().lower()
        if h.startswith('sol'):
            bolge = _birincil_ekran()
            yon_adi = 'sol'
        else:
            bolge = _sag_ekran()
            yon_adi = 'sag'
        b = str(baslik or '').strip()
        if b:
            hwnd, ad = _hwnd_bul(b)
            if not hwnd:
                return ad
        else:
            hwnd = _aktif_hwnd()
            ad = 'aktif pencere'
            if not hwnd:
                return 'Aktif pencere bulunamadi.'
        # Yontem 1: restore + SetWindowPos
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.2)
        except Exception:
            pass
        gen = 1100
        yuk = 700
        x = bolge[0] + max(0, (bolge[2] - bolge[0] - gen) // 2)
        y = bolge[1] + max(0, (bolge[3] - bolge[1] - yuk) // 2)
        try:
            win32gui.SetWindowPos(hwnd, 0, x, y, gen, yuk, 0x0040)
            time.sleep(0.4)
        except Exception as e:
            return ('Tasima komutu verilemedi: ' + str(e)[:150] +
                    '. "Tasidim" DEME.')
        kutu = _pencere_bolge(hwnd)
        if _bolgede_mi(kutu, bolge):
            return ('Tasindi (dogrulandi, ' + yon_adi + ' ekran): ' +
                    _guvenli(ad)[:100])
        # Yontem 2: Win+Shift+Sag/Sol (farkli yontem, ayni seyin tekrari degil)
        try:
            from pywinauto import keyboard
            tus = '#+{RIGHT}' if yon_adi == 'sag' else '#+{LEFT}'
            pencere_odakla(ad if b else '')
            time.sleep(0.2)
            keyboard.send_keys(tus)
            time.sleep(0.5)
        except Exception:
            pass
        kutu = _pencere_bolge(hwnd)
        if _bolgede_mi(kutu, bolge):
            return ('Tasindi (dogrulandi, ' + yon_adi + ' ekran): ' +
                    _guvenli(ad)[:100])
        return ('Tasima iki yontemle denendi ama pencere ' + yon_adi +
                ' ekrana GECMEDI (' + _guvenli(ad)[:60] + '). "Tasidim" DEME; '
                'manuel suruklemeyi oner.')
    except Exception as e:
        return 'Tasima basarisiz: ' + str(e)[:200]


def dosya_bul(ad, surucu='C:\\', derinlik=3):
    """Diskte dosya/klasor ARAR. Konum sorulmadan once kullanilir."""
    try:
        import subprocess
        a = str(ad or '').strip()
        if not a:
            return 'Aranacak ad verilmedi.'
        try:
            d = max(1, min(int(derinlik), 5))
        except Exception:
            d = 3
        kok = str(surucu or 'C:\\').strip() or 'C:\\'
        ps = ('Get-ChildItem -LiteralPath \'' + kok.replace('\'', '\'\'') +
              '\' -Recurse -Depth ' + str(d) +
              ' -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like \'*' +
              a.replace('\'', '\'\'') + '*\' } | Select-Object -First 10 -ExpandProperty FullName')
        r = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive',
             '-ExecutionPolicy', 'Bypass', '-Command', ps],
            capture_output=True, text=True, timeout=60,
            encoding='utf-8', errors='replace',
        )
        cikti = (r.stdout or '').strip()
        if cikti:
            satirlar = [s for s in cikti.splitlines() if s.strip()]
            return ('Bulundu (' + str(len(satirlar)) + '):\n' +
                    '\n'.join(satirlar[:10]))
        # Klasor degilse dosya dene
        ps2 = ('Get-ChildItem -LiteralPath \'' + kok.replace('\'', '\'\'') +
               '\' -Recurse -Depth ' + str(d) +
               ' -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like \'*' +
               a.replace('\'', '\'\'') + '*\' } | Select-Object -First 10 -ExpandProperty FullName')
        r2 = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive',
             '-ExecutionPolicy', 'Bypass', '-Command', ps2],
            capture_output=True, text=True, timeout=60,
            encoding='utf-8', errors='replace',
        )
        cikti2 = (r2.stdout or '').strip()
        if cikti2:
            satirlar = [s for s in cikti2.splitlines() if s.strip()]
            return ('Bulundu (' + str(len(satirlar)) + '):\n' +
                    '\n'.join(satirlar[:10]))
        return ('Bulunamadi: ' + a[:80] + ' (' + kok + ', derinlik ' +
                str(d) + '). Simdi kullaniciya sorabilirsin.')
    except subprocess.TimeoutExpired:
        return 'Arama zaman asimina ugradi (60sn). Daha dar bir surucu/depth dene.'
    except Exception as e:
        return 'Arama basarisiz: ' + str(e)[:200]
