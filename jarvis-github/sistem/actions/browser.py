"""
Tarayici kontrolu — varsayilan tarayici ile calisir (macOS + Windows).
"""

import re
import urllib.parse
import webbrowser

import requests

from actions.platform_utils import IS_WIN, open_path


YOUTUBE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ) if IS_WIN else (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _open(url: str) -> None:
    ok, _ = open_path(url)
    if not ok:
        # Son care: Python'un kendi tarayici baslaticisi
        try:
            webbrowser.open(url)
        except Exception:
            pass


def _find_first_youtube_video(query: str) -> str | None:
    search_url = "https://www.youtube.com/results"
    response = requests.get(
        search_url,
        params={"search_query": query},
        headers=YOUTUBE_HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    html = response.text

    matches = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
    seen = set()
    for video_id in matches:
        if video_id not in seen:
            seen.add(video_id)
            return video_id

    matches = re.findall(r'/watch\?v=([A-Za-z0-9_-]{11})', html)
    for video_id in matches:
        if video_id not in seen:
            seen.add(video_id)
            return video_id

    return None


def browser_control(action: str, url: str = None, query: str = None) -> str:
    if action == "open_url":
        if not url:
            return "URL belirtilmedi."
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        _open(url)
        return f"Acildi: {url}"

    elif action == "search":
        if not query:
            return "Arama sorgusu belirtilmedi."
        encoded = urllib.parse.quote(query)
        search_url = f"https://www.google.com/search?q={encoded}"
        _open(search_url)
        return f"'{query}' icin arama acildi."

    elif action in ("play_youtube", "youtube_play", "play_music"):
        if not query:
            return "YouTube icin arama sorgusu belirtilmedi."

        try:
            video_id = _find_first_youtube_video(query)
        except Exception as exc:
            encoded = urllib.parse.quote(query)
            fallback_url = f"https://www.youtube.com/results?search_query={encoded}"
            _open(fallback_url)
            return (
                f"YouTube ilk sonucu alinamadi ({exc}). "
                f"Arama sonuclari acildi: {query}"
            )

        if not video_id:
            encoded = urllib.parse.quote(query)
            fallback_url = f"https://www.youtube.com/results?search_query={encoded}"
            _open(fallback_url)
            return f"YouTube'da dogrudan video bulunamadi. Arama sonuclari acildi: {query}"

        watch_url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
        _open(watch_url)
        return f"YouTube'da oynatiliyor: {query}"

    return f"Bilinmeyen eylem: {action}"
