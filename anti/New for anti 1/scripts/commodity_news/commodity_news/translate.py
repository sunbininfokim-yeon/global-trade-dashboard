"""Optional free translation (MyMemory) for Korean main ticker titles."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional

from .score import ScoredItem


def translate_mymemory(
    text: str,
    *,
    source_lang: str,
    target_lang: str = "ko",
    email: Optional[str] = None,
    timeout: float = 12.0,
) -> Optional[str]:
    if not text or not text.strip():
        return None
    src = source_lang.split("-")[0] if source_lang else "en"
    if src == target_lang or (src.startswith("ko") and target_lang.startswith("ko")):
        return text
    # MyMemory uses ISO pairs
    if src in {"zh", "zh-TW", "zh-HK"}:
        src = "zh-CN" if src == "zh" else "zh-TW"
    pair = f"{src}|{target_lang}"
    q = urllib.parse.urlencode(
        {
            "q": text[:450],
            "langpair": pair,
            **({"de": email} if email else {}),
        }
    )
    url = f"https://api.mymemory.translated.net/get?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "GTradeTicker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    if payload.get("responseStatus") != 200:
        return None
    translated = (payload.get("responseData") or {}).get("translatedText")
    if not translated:
        return None
    # MyMemory sometimes echoes "MYMEMORY WARNING..." into the text.
    if "MYMEMORY WARNING" in translated.upper():
        return None
    return translated.strip()


def apply_korean_titles(
    items: list[ScoredItem],
    *,
    enabled: bool,
    email: Optional[str] = None,
    sleep_sec: float = 0.35,
    cache: Optional[Dict[str, str]] = None,
) -> None:
    """Mutate items in place: set title_ko + translation_status."""
    cache = cache if cache is not None else {}
    for it in items:
        if it.original_lang in {"ko", "ko-KR"}:
            it.title_ko = it.title_original
            it.translation_status = "ok"
            continue
        if not enabled:
            it.translation_status = "skipped"
            continue
        key = f"{it.original_lang}|{it.title_original}"
        if key in cache:
            it.title_ko = cache[key]
            it.translation_status = "ok"
            continue
        translated = translate_mymemory(
            it.title_original, source_lang=it.original_lang, target_lang="ko", email=email
        )
        if translated:
            it.title_ko = translated
            it.translation_status = "ok"
            cache[key] = translated
        else:
            it.translation_status = "failed"
        time.sleep(sleep_sec)
