"""L0 — DART OpenAPI client (no key required for fixture / offline mode)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE = "https://opendart.fss.or.kr/api"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


class DartApiError(RuntimeError):
    pass


def api_key_from_env() -> str | None:
    for name in ("DART_API_KEY", "OPENDART_API_KEY", "DART_KEY"):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return None


def _cache_path(kind: str, parts: dict[str, str]) -> Path:
    key = "_".join(f"{k}-{v}" for k, v in sorted(parts.items()))
    return CACHE_DIR / f"{kind}__{key}.json"


def _http_get_json(url: str, timeout: float = 30.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "kfa-engine/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise DartApiError(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise DartApiError(f"network error: {e}") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise DartApiError("response is not JSON") from e


def fetch_fnltt_singl_acnt_all(
    *,
    corp_code: str,
    bsns_year: str | int,
    reprt_code: str = "11011",
    fs_div: str = "CFS",
    api_key: str | None = None,
    use_cache: bool = True,
    base_url: str = DEFAULT_BASE,
) -> dict[str, Any]:
    """Fetch full single-company financial statements.

    Requires a free OpenDART API key. While waiting for the key, call
    ``load_fixture`` instead.
    """
    key = api_key or api_key_from_env()
    if not key:
        raise DartApiError(
            "DART_API_KEY not set. Export the OpenDART key, or use --fixture."
        )

    year = str(bsns_year)
    cache_parts = {
        "corp": corp_code,
        "year": year,
        "reprt": reprt_code,
        "fs": fs_div,
    }
    cpath = _cache_path("fnltt", cache_parts)
    if use_cache and cpath.exists():
        with cpath.open(encoding="utf-8") as f:
            return json.load(f)

    params = urllib.parse.urlencode(
        {
            "crtfc_key": key,
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        }
    )
    url = f"{base_url}/fnlttSinglAcntAll.json?{params}"
    payload = _http_get_json(url)
    status = str(payload.get("status") or "")
    if status not in {"000", "0"}:
        raise DartApiError(
            f"DART status={status} message={payload.get('message')}"
        )

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with cpath.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

    # gentle pacing if callers loop
    time.sleep(0.05)
    return payload


def load_fixture(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("list")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]
