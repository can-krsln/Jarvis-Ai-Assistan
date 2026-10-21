"""
Windows takvim + animsatici arka ucu.

Iki arka uc destekler:

1. "local"   — JARVIS'in kendi JSON deposu. Her Windows makinesinde calisir,
               hicbir kuruluma bagli degildir. Yaninda .ics kopyasi da uretir,
               boylece Outlook/Google Takvim'e ice aktarilabilir.
2. "outlook" — Klasik Outlook (COM/MAPI). Kullanicinin gercek takvimini okur
               ve yazar.

Secim `config/api_keys.json` icindeki `calendar_backend` anahtariyla yapilir:
  "auto"    (varsayilan) → Outlook ZATEN ACIKSA onu kullanir, degilse yerel depo.
                           Outlook'u kendisi baslatmaz; yapilandirilmamis bir
                           Outlook'ta acilan kurulum sihirbazi JARVIS'i kilitler.
  "outlook"             → Outlook'u zorlar (gerekirse baslatir).
  "local"               → Her zaman yerel depo.

Tum Outlook cagrilari zaman asimi korumasiyla ayri bir thread'de calisir;
Outlook takilirsa JARVIS donmaz, sessizce yerel depoya duser.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import uuid
from pathlib import Path

from app_config import get_app_config_value
from actions.platform_utils import com_context


from app_paths import data_path

BASE_DIR = Path(__file__).resolve().parent.parent
# Takvim ve animsaticilar kullanici verisidir → yazilabilir koke
STORE_PATH = data_path("memory", "calendar_store.json")
ICS_PATH = data_path("memory", "jarvis_calendar.ics")

OUTLOOK_TIMEOUT = 12.0

# Outlook klasor sabitleri
OL_FOLDER_CALENDAR = 9
OL_FOLDER_TASKS = 13

_store_lock = threading.Lock()
_backend_cache: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# Arka uc secimi
# ═══════════════════════════════════════════════════════════════════════════
def _configured_backend() -> str:
    value = str(get_app_config_value("calendar_backend", "auto") or "auto").strip().lower()
    if value not in {"auto", "outlook", "local"}:
        return "auto"
    return value


def active_backend(refresh: bool = False) -> str:
    """Bu calistirmada hangi arka ucun kullanilacagini belirler → 'outlook'|'local'."""
    global _backend_cache
    if _backend_cache is not None and not refresh:
        return _backend_cache

    mode = _configured_backend()
    if mode == "local":
        _backend_cache = "local"
    elif mode == "outlook":
        _backend_cache = "outlook" if _probe_outlook(allow_launch=True) else "local"
    else:
        # auto: yalnizca Outlook zaten calisiyorsa kullan
        _backend_cache = "outlook" if _probe_outlook(allow_launch=False) else "local"

    return _backend_cache


def backend_label() -> str:
    return "Outlook" if active_backend() == "outlook" else "JARVIS yerel takvimi"


def _probe_outlook(allow_launch: bool) -> bool:
    """Outlook MAPI erisilebilir mi? Asla kilitlenmez."""
    def work():
        with com_context():
            return _probe_outlook_inner(allow_launch)

    try:
        return bool(_run_with_timeout(work, OUTLOOK_TIMEOUT))
    except Exception:
        return False


def _probe_outlook_inner(allow_launch: bool) -> bool:
    import win32com.client

    try:
        if allow_launch:
            app = win32com.client.Dispatch("Outlook.Application")
        else:
            # GetActiveObject yalnizca calisan bir Outlook'a baglanir,
            # yenisini BASLATMAZ — kurulum sihirbazi riski olmaz.
            app = win32com.client.GetActiveObject("Outlook.Application")
    except Exception:
        return False

    try:
        namespace = app.GetNamespace("MAPI")
        folder = namespace.GetDefaultFolder(OL_FOLDER_CALENDAR)
        _ = folder.Name
        return True
    except Exception:
        return False


def _run_with_timeout(fn, timeout: float):
    """
    Fonksiyonu ayri bir thread'de calistirir; sure asilirsa TimeoutError.
    COM nesneleri thread'ler arasi tasinamadigi icin isin tamami bu
    thread'in icinde biter.
    """
    box: dict = {}

    def runner():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise TimeoutError("Outlook yanit vermedi.")
    if "error" in box:
        raise box["error"]
    return box.get("value")


# ═══════════════════════════════════════════════════════════════════════════
# Yerel depo
# ═══════════════════════════════════════════════════════════════════════════
def _empty_store() -> dict:
    return {"events": [], "reminders": []}


def _load_store() -> dict:
    try:
        raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _empty_store()
        raw.setdefault("events", [])
        raw.setdefault("reminders", [])
        if not isinstance(raw["events"], list):
            raw["events"] = []
        if not isinstance(raw["reminders"], list):
            raw["reminders"] = []
        return raw
    except Exception:
        return _empty_store()


def _save_store(store: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(
        json.dumps(store, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        _write_ics(store)
    except Exception:
        pass


def _write_ics(store: dict) -> None:
    """Yerel takvimi .ics olarak da yazar — baska takvimlere ice aktarilabilir."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//JARVIS//Windows//TR",
        "CALSCALE:GREGORIAN",
    ]
    for event in store.get("events", []):
        try:
            start = dt.datetime.fromisoformat(event["start_iso"])
            end = dt.datetime.fromisoformat(event["end_iso"])
        except Exception:
            continue
        all_day = bool(event.get("all_day"))
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{event.get('id', uuid.uuid4().hex)}@jarvis")
        lines.append("DTSTAMP:" + dt.datetime.now().strftime("%Y%m%dT%H%M%S"))
        if all_day:
            lines.append("DTSTART;VALUE=DATE:" + start.strftime("%Y%m%d"))
            lines.append("DTEND;VALUE=DATE:" + end.strftime("%Y%m%d"))
        else:
            lines.append("DTSTART:" + start.strftime("%Y%m%dT%H%M%S"))
            lines.append("DTEND:" + end.strftime("%Y%m%dT%H%M%S"))
        lines.append("SUMMARY:" + _ics_escape(str(event.get("title", ""))))
        if event.get("location"):
            lines.append("LOCATION:" + _ics_escape(str(event["location"])))
        if event.get("notes"):
            lines.append("DESCRIPTION:" + _ics_escape(str(event["notes"])))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    ICS_PATH.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


# ═══════════════════════════════════════════════════════════════════════════
# Tarih yardimcilari
# ═══════════════════════════════════════════════════════════════════════════
def parse_iso(value: str, default_all_day: bool = False) -> tuple[dt.datetime | None, bool]:
    """Esnek ISO/yerel tarih ayristirici → (datetime, tum_gun_mu)."""
    raw = (value or "").strip()
    if not raw:
        return None, default_all_day

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        parsed = dt.datetime.fromisoformat(raw)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        is_date_only = len(raw) == 10
        return parsed, is_date_only
    except ValueError:
        pass

    formats = (
        ("%Y-%m-%d %H:%M:%S", False),
        ("%Y-%m-%d %H:%M", False),
        ("%d.%m.%Y %H:%M", False),
        ("%d/%m/%Y %H:%M", False),
        ("%Y-%m-%d", True),
        ("%d.%m.%Y", True),
        ("%d/%m/%Y", True),
    )
    for fmt, all_day in formats:
        try:
            return dt.datetime.strptime(raw, fmt), all_day
        except ValueError:
            continue

    return None, default_all_day


def _to_ts(value: dt.datetime) -> int:
    return int(value.timestamp())


def _event_from_record(record: dict) -> dict | None:
    try:
        start = dt.datetime.fromisoformat(record["start_iso"])
        end = dt.datetime.fromisoformat(record["end_iso"])
    except Exception:
        return None
    return {
        "start_ts": _to_ts(start),
        "end_ts": _to_ts(end),
        "calendar": str(record.get("calendar_name", "") or "JARVIS"),
        "title": str(record.get("title", "")).strip() or "Adsiz etkinlik",
        "location": str(record.get("location", "") or ""),
        "all_day": bool(record.get("all_day", False)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Etkinlikler
# ═══════════════════════════════════════════════════════════════════════════
def fetch_events(start: dt.datetime, end: dt.datetime) -> tuple[bool, str, list[dict]]:
    if active_backend() == "outlook":
        try:
            return True, "", _outlook_fetch_events(start, end)
        except Exception:
            # Outlook bir sekilde cevap vermedi — yerel depoya dus.
            pass
    return True, "", _local_fetch_events(start, end)


def _local_fetch_events(start: dt.datetime, end: dt.datetime) -> list[dict]:
    with _store_lock:
        store = _load_store()

    start_ts, end_ts = _to_ts(start), _to_ts(end)
    events = []
    for record in store["events"]:
        event = _event_from_record(record)
        if not event:
            continue
        # Araligi kesen her etkinlik dahil
        if event["end_ts"] > start_ts and event["start_ts"] < end_ts:
            events.append(event)
    return events


def _outlook_fetch_events(start: dt.datetime, end: dt.datetime) -> list[dict]:
    def work():
        with com_context():
            return _outlook_fetch_events_inner(start, end)

    return _run_with_timeout(work, OUTLOOK_TIMEOUT) or []


def _outlook_fetch_events_inner(start: dt.datetime, end: dt.datetime) -> list[dict]:
    import win32com.client

    app = win32com.client.Dispatch("Outlook.Application")
    namespace = app.GetNamespace("MAPI")
    folder = namespace.GetDefaultFolder(OL_FOLDER_CALENDAR)

    items = folder.Items
    items.IncludeRecurrences = True
    items.Sort("[Start]")

    # Outlook'un Restrict tarih bicimi ABD yerel ayarini bekler.
    fmt = "%m/%d/%Y %I:%M %p"
    restriction = (
        f"[End] >= '{start.strftime(fmt)}' AND [Start] <= '{end.strftime(fmt)}'"
    )
    try:
        selected = items.Restrict(restriction)
    except Exception:
        selected = items

    results: list[dict] = []
    count = 0
    for item in selected:
        count += 1
        if count > 400:  # yinelenen etkinliklerde sonsuz genislemeyi kes
            break
        try:
            item_start = _com_datetime(item.Start)
            item_end = _com_datetime(item.End)
            if item_start is None or item_end is None:
                continue
            if item_end < start or item_start > end:
                continue
            results.append(
                {
                    "start_ts": _to_ts(item_start),
                    "end_ts": _to_ts(item_end),
                    "calendar": str(getattr(folder, "Name", "") or "Outlook"),
                    "title": str(getattr(item, "Subject", "") or "").strip() or "Adsiz etkinlik",
                    "location": str(getattr(item, "Location", "") or ""),
                    "all_day": bool(getattr(item, "AllDayEvent", False)),
                }
            )
        except Exception:
            continue
    return results


def _com_datetime(value) -> dt.datetime | None:
    """pywin32 COM tarihini saf datetime'a cevirir."""
    try:
        naive = dt.datetime(
            value.year, value.month, value.day,
            value.hour, value.minute, value.second,
        )
        return naive
    except Exception:
        try:
            return dt.datetime.fromisoformat(str(value))
        except Exception:
            return None


def create_event(payload: dict) -> tuple[bool, str, dict | None]:
    title = str(payload.get("title", "")).strip()
    start, start_all_day = parse_iso(str(payload.get("start_iso", "")))
    if start is None:
        return False, "Baslangic tarihi anlasilamadi. 'YYYY-MM-DD' veya 'YYYY-MM-DDTHH:MM' kullan.", None

    all_day = bool(payload.get("all_day", False)) or start_all_day

    end, _ = parse_iso(str(payload.get("end_iso", "")))
    if end is None:
        if all_day:
            end = (start + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            end = start + dt.timedelta(hours=1)
    if end <= start:
        end = start + (dt.timedelta(days=1) if all_day else dt.timedelta(hours=1))

    record = {
        "id": uuid.uuid4().hex,
        "title": title,
        "start_iso": start.isoformat(),
        "end_iso": end.isoformat(),
        "notes": str(payload.get("notes", "") or ""),
        "location": str(payload.get("location", "") or ""),
        "calendar_name": str(payload.get("calendar_name", "") or ""),
        "all_day": all_day,
    }

    if active_backend() == "outlook":
        try:
            created = _outlook_create_event(record)
            if created:
                return True, "", created
        except Exception:
            pass

    with _store_lock:
        store = _load_store()
        store["events"].append(record)
        _save_store(store)

    event = _event_from_record(record)
    if not event:
        return False, "Etkinlik kaydedildi ama okunamadi.", None
    if not record["calendar_name"]:
        event["calendar"] = "JARVIS"
    return True, "", event


def _outlook_create_event(record: dict) -> dict | None:
    def work():
        with com_context():
            return _outlook_create_event_inner(record)

    return _run_with_timeout(work, OUTLOOK_TIMEOUT)


def _outlook_create_event_inner(record: dict) -> dict | None:
    import win32com.client

    app = win32com.client.Dispatch("Outlook.Application")
    appointment = app.CreateItem(1)  # olAppointmentItem
    start = dt.datetime.fromisoformat(record["start_iso"])
    end = dt.datetime.fromisoformat(record["end_iso"])

    appointment.Subject = record["title"]
    appointment.Start = start.strftime("%Y-%m-%d %H:%M")
    if record["all_day"]:
        appointment.AllDayEvent = True
    else:
        appointment.End = end.strftime("%Y-%m-%d %H:%M")
    if record["location"]:
        appointment.Location = record["location"]
    if record["notes"]:
        appointment.Body = record["notes"]
    appointment.Save()

    return {
        "start_ts": _to_ts(start),
        "end_ts": _to_ts(end),
        "calendar": "Outlook",
        "title": record["title"] or "Adsiz etkinlik",
        "location": record["location"],
        "all_day": record["all_day"],
    }


def delete_event(payload: dict) -> tuple[bool, str, dict | None, list[dict]]:
    """→ (basarili, hata, silinen_etkinlik, eslesen_etkinlikler)"""
    title = str(payload.get("title", "")).strip()
    needle = title.casefold()
    start_filter, _ = parse_iso(str(payload.get("start_iso", "")))
    delete_all = bool(payload.get("delete_all_matches", False))

    if active_backend() == "outlook":
        try:
            ok, detail, deleted, matches = _outlook_delete_event(title, start_filter, delete_all)
            if ok or matches:
                return ok, detail, deleted, matches
        except Exception:
            pass

    with _store_lock:
        store = _load_store()
        matched_indexes = []
        for index, record in enumerate(store["events"]):
            if needle not in str(record.get("title", "")).casefold():
                continue
            if start_filter is not None:
                try:
                    record_start = dt.datetime.fromisoformat(record["start_iso"])
                except Exception:
                    continue
                if abs((record_start - start_filter).total_seconds()) > 3600:
                    continue
            matched_indexes.append(index)

        if not matched_indexes:
            return False, f"'{title}' baslikli bir etkinlik bulunamadi.", None, []

        matches = [
            event for event in (_event_from_record(store["events"][i]) for i in matched_indexes)
            if event
        ]

        if len(matched_indexes) > 1 and not delete_all:
            return (
                False,
                f"'{title}' ile eslesen {len(matched_indexes)} etkinlik var. "
                "Hangisini silecegimi belirt (baslangic saatiyle) ya da tumunu sil.",
                None,
                matches,
            )

        removed = [store["events"][i] for i in matched_indexes]
        for index in sorted(matched_indexes, reverse=True):
            store["events"].pop(index)
        _save_store(store)

    deleted_event = _event_from_record(removed[0])
    return True, "", deleted_event, matches


def _outlook_delete_event(
    title: str, start_filter: dt.datetime | None, delete_all: bool
) -> tuple[bool, str, dict | None, list[dict]]:
    def work():
        with com_context():
            return _outlook_delete_event_inner(title, start_filter, delete_all)

    return _run_with_timeout(work, OUTLOOK_TIMEOUT)


def _outlook_delete_event_inner(
    title: str, start_filter: dt.datetime | None, delete_all: bool
) -> tuple[bool, str, dict | None, list[dict]]:
    import win32com.client

    app = win32com.client.Dispatch("Outlook.Application")
    namespace = app.GetNamespace("MAPI")
    folder = namespace.GetDefaultFolder(OL_FOLDER_CALENDAR)

    needle = title.casefold()
    candidates = []
    count = 0
    for item in folder.Items:
        count += 1
        if count > 800:
            break
        try:
            subject = str(getattr(item, "Subject", "") or "")
            if needle not in subject.casefold():
                continue
            item_start = _com_datetime(item.Start)
            if item_start is None:
                continue
            if start_filter is not None and abs((item_start - start_filter).total_seconds()) > 3600:
                continue
            candidates.append((item, item_start))
        except Exception:
            continue

    if not candidates:
        return False, f"'{title}' baslikli bir etkinlik bulunamadi.", None, []

    matches = []
    for item, item_start in candidates:
        try:
            item_end = _com_datetime(item.End) or item_start
            matches.append(
                {
                    "start_ts": _to_ts(item_start),
                    "end_ts": _to_ts(item_end),
                    "calendar": "Outlook",
                    "title": str(getattr(item, "Subject", "") or "") or "Adsiz etkinlik",
                    "location": str(getattr(item, "Location", "") or ""),
                    "all_day": bool(getattr(item, "AllDayEvent", False)),
                }
            )
        except Exception:
            continue

    if len(candidates) > 1 and not delete_all:
        return (
            False,
            f"'{title}' ile eslesen {len(candidates)} etkinlik var. "
            "Hangisini silecegimi belirt (baslangic saatiyle) ya da tumunu sil.",
            None,
            matches,
        )

    deleted = matches[0] if matches else None
    for item, _ in candidates:
        try:
            item.Delete()
        except Exception:
            continue
        if not delete_all:
            break

    return True, "", deleted, matches


# ═══════════════════════════════════════════════════════════════════════════
# Animsaticilar
# ═══════════════════════════════════════════════════════════════════════════
def _reminder_from_record(record: dict) -> dict:
    due_ts = 0
    if record.get("due_iso"):
        try:
            due_ts = _to_ts(dt.datetime.fromisoformat(record["due_iso"]))
        except Exception:
            due_ts = 0
    return {
        "title": str(record.get("title", "")).strip() or "Adsiz animsatici",
        "list_name": str(record.get("list_name", "") or ""),
        "notes": str(record.get("notes", "") or ""),
        "completed": bool(record.get("completed", False)),
        "priority": int(record.get("priority", 0) or 0),
        "due_ts": due_ts,
        "all_day": bool(record.get("all_day", False)),
    }


def fetch_reminders(mode: str, limit: int, list_name: str = "") -> tuple[bool, str, list[dict]]:
    if active_backend() == "outlook":
        try:
            items = _outlook_fetch_reminders(list_name)
            return True, "", _filter_reminders(items, mode, limit)
        except Exception:
            pass

    with _store_lock:
        store = _load_store()
    items = [_reminder_from_record(record) for record in store["reminders"]]
    if list_name:
        needle = list_name.casefold()
        items = [item for item in items if needle in item["list_name"].casefold()]
    return True, "", _filter_reminders(items, mode, limit)


def _filter_reminders(items: list[dict], mode: str, limit: int) -> list[dict]:
    now = dt.datetime.now()
    now_ts = _to_ts(now)
    today_end = _to_ts(now.replace(hour=23, minute=59, second=59, microsecond=0))

    open_items = [item for item in items if not item["completed"]]

    if mode == "today":
        selected = [i for i in open_items if 0 < i["due_ts"] <= today_end]
    elif mode == "overdue":
        selected = [i for i in open_items if 0 < i["due_ts"] < now_ts]
    elif mode == "next":
        selected = [i for i in open_items if i["due_ts"] >= now_ts]
    elif mode == "all":
        selected = open_items
    else:  # upcoming
        selected = [i for i in open_items if i["due_ts"] == 0 or i["due_ts"] >= now_ts]

    selected.sort(key=lambda item: (item["due_ts"] <= 0, item["due_ts"] or 0, item["title"].lower()))
    return selected[: max(1, limit)]


def _outlook_fetch_reminders(list_name: str) -> list[dict]:
    def work():
        with com_context():
            return _outlook_fetch_reminders_inner()

    return _run_with_timeout(work, OUTLOOK_TIMEOUT) or []


def _outlook_fetch_reminders_inner() -> list[dict]:
    import win32com.client

    app = win32com.client.Dispatch("Outlook.Application")
    namespace = app.GetNamespace("MAPI")
    folder = namespace.GetDefaultFolder(OL_FOLDER_TASKS)

    results = []
    count = 0
    for item in folder.Items:
        count += 1
        if count > 400:
            break
        try:
            due_ts = 0
            due = _com_datetime(getattr(item, "DueDate", None))
            # Outlook tarih atanmamis gorevlerde 1/1/4501 dondurur
            if due is not None and due.year < 4000:
                due_ts = _to_ts(due)
            results.append(
                {
                    "title": str(getattr(item, "Subject", "") or "").strip() or "Adsiz animsatici",
                    "list_name": "Outlook",
                    "notes": str(getattr(item, "Body", "") or "").strip(),
                    "completed": bool(getattr(item, "Complete", False)),
                    "priority": 1 if int(getattr(item, "Importance", 1) or 1) == 2 else 0,
                    "due_ts": due_ts,
                    "all_day": True,
                }
            )
        except Exception:
            continue
    return results


def create_reminder(payload: dict) -> tuple[bool, str, dict | None]:
    title = str(payload.get("title", "")).strip()
    if not title:
        return False, "Animsatici basligi bos olamaz.", None

    due_iso = ""
    all_day = bool(payload.get("all_day", False))
    raw_due = str(payload.get("due_iso", "") or "").strip()
    if raw_due:
        due, inferred_all_day = parse_iso(raw_due)
        if due is None:
            return (
                False,
                "Animsatici tarihi gecersiz. due_iso icin 'YYYY-MM-DD' veya 'YYYY-MM-DDTHH:MM' kullan.",
                None,
            )
        due_iso = due.isoformat()
        all_day = all_day or inferred_all_day

    priority_raw = str(payload.get("priority", "") or "").strip().lower()
    priority = 1 if priority_raw in {"high", "yuksek", "yüksek", "1"} else 0

    record = {
        "id": uuid.uuid4().hex,
        "title": title,
        "due_iso": due_iso,
        "notes": str(payload.get("notes", "") or ""),
        "list_name": str(payload.get("list_name", "") or ""),
        "priority": priority,
        "all_day": all_day,
        "completed": False,
    }

    if active_backend() == "outlook":
        try:
            created = _outlook_create_reminder(record)
            if created:
                return True, "", created
        except Exception:
            pass

    with _store_lock:
        store = _load_store()
        store["reminders"].append(record)
        _save_store(store)

    return True, "", _reminder_from_record(record)


def _outlook_create_reminder(record: dict) -> dict | None:
    def work():
        with com_context():
            return _outlook_create_reminder_inner(record)

    return _run_with_timeout(work, OUTLOOK_TIMEOUT)


def _outlook_create_reminder_inner(record: dict) -> dict | None:
    import win32com.client

    app = win32com.client.Dispatch("Outlook.Application")
    task = app.CreateItem(3)  # olTaskItem
    task.Subject = record["title"]
    if record["due_iso"]:
        due = dt.datetime.fromisoformat(record["due_iso"])
        task.DueDate = due.strftime("%Y-%m-%d %H:%M")
    if record["notes"]:
        task.Body = record["notes"]
    if record["priority"] == 1:
        task.Importance = 2
    task.Save()

    result = _reminder_from_record(record)
    result["list_name"] = "Outlook"
    return result
