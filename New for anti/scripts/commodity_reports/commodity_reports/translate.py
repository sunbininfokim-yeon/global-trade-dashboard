"""Optional Korean headlines (MyMemory free tier), same service the ticker uses.

Off by default. The free quota is small and the calls are slow, so a build
that translates everything would either fail or take longer than the cron
window; the card falls back to the original headline whenever `ko` is null,
which is the normal state until an operator opts in with --translate.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

from .score import ScoredReport


def translate_mymemory(
    text: str, *, source_lang: str, target_lang: str = "ko", timeout: float = 12.0
) -> Optional[str]:
    if not text.strip():
        return None
    src = (source_lang or "en").split("-")[0]
    if src == target_lang:
        return text
    query = urllib.parse.urlencode({"q": text[:450], "langpair": f"{src}|{target_lang}"})
    req = urllib.request.Request(
        f"https://api.mymemory.translated.net/get?{query}",
        headers={"User-Agent": "GlobalTradeDashboard-CommodityReports/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    if payload.get("responseStatus") != 200:
        return None
    out = (payload.get("responseData") or {}).get("translatedText") or ""
    # MyMemory writes its quota warnings into the translated text itself.
    if not out or "MYMEMORY WARNING" in out.upper():
        return None
    return out.strip()


def apply_korean_titles(reports: List[ScoredReport], *, limit: int = 60, pause: float = 0.4) -> int:
    """Translate the top `limit` headlines in place; returns how many landed."""
    done = 0
    for r in reports[:limit]:
        if r.lang.startswith("ko"):
            r.title_ko = r.title
            continue
        ko = translate_mymemory(r.title, source_lang=r.lang)
        if ko and ko != r.title:
            r.title_ko = ko
            done += 1
        time.sleep(pause)
    return done
