"""Lightweight language helpers (no external ML deps)."""

from __future__ import annotations

import re
from typing import Optional


_HANGUL = re.compile(r"[\uac00-\ud7a3]")
_HIRAGANA = re.compile(r"[\u3040-\u309f]")
_KATAKANA = re.compile(r"[\u30a0-\u30ff]")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_ARABIC = re.compile(r"[\u0600-\u06ff]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_DEVANAGARI = re.compile(r"[\u0900-\u097f]")


def detect_lang(text: str, fallback: str = "en") -> str:
    if not text:
        return fallback
    sample = text[:800]
    counts = {
        "ko": len(_HANGUL.findall(sample)),
        "ja": len(_HIRAGANA.findall(sample)) + len(_KATAKANA.findall(sample)),
        "zh": len(_CJK.findall(sample)),
        "ar": len(_ARABIC.findall(sample)),
        "ru": len(_CYRILLIC.findall(sample)),
        "hi": len(_DEVANAGARI.findall(sample)),
    }
    # Prefer Japanese when kana present even if CJK also appears.
    if counts["ja"] >= 3:
        return "ja"
    best = max(counts, key=counts.get)
    if counts[best] >= 4:
        if best == "zh":
            # Cannot distinguish TW/HK reliably without metadata.
            return "zh"
        return best
    return fallback


def normalize_lang_tag(tag: Optional[str]) -> str:
    if not tag:
        return "en"
    t = tag.replace("_", "-").strip().lower()
    if t.startswith("zh-tw") or t.startswith("zh-hant"):
        return "zh-TW"
    if t.startswith("zh-hk"):
        return "zh-HK"
    if t.startswith("zh"):
        return "zh"
    if "-" in t:
        return t.split("-", 1)[0]
    return t
