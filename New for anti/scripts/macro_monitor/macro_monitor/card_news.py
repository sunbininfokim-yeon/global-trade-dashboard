"""News beside the US macro cards: official releases first, press articles behind a toggle. Free, keyless.

official  the agency that publishes the number, newest first:
          Fed monetary-policy press RSS (federalreserve.gov/feeds/press_monetary.xml),
          BEA RSS (apps.bea.gov/rss/rss.xml, items carry the release name),
          Treasury debt-management releases already collected in config/ust_toolkit_feed_v1.json,
          BLS: bls.gov refuses automated clients (403), so the card links the release's 'latest' page instead
          of reading it -- no fetch, no workaround.
press     Google News RSS search (English and Korean) with a per-card query, kept only when the headline names
          the card's subject (REQUIRE), within the last 45 days.

Written onto each card as `news_official` and `news_press` (lists of {title, url, source, published_at});
macro.js mmNewsRail shows the official list with a toggle to the press list.
"""

from __future__ import annotations

import html as _html
import json
import re
import subprocess
import time
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

FED = "https://www.federalreserve.gov/feeds/press_monetary.xml"
BEA = "https://apps.bea.gov/rss/rss.xml"
TREASURY_STORE = Path(__file__).resolve().parents[1] / "config" / "ust_toolkit_feed_v1.json"
GNEWS = "https://news.google.com/rss/search?q={q}&{loc}"
LOC = {"en": "hl=en-US&gl=US&ceid=US:en", "ko": "hl=ko&gl=KR&ceid=KR:ko"}
KEEP_OFFICIAL, KEEP_PRESS, PRESS_DAYS = 6, 8, 45

BLS_LINKS = {
    "cpi": ("BLS 소비자물가지수(CPI) 보도자료 — 최신", "https://www.bls.gov/news.release/cpi.nr0.htm"),
    "jobs": ("BLS 고용상황(Employment Situation) 보도자료 — 최신", "https://www.bls.gov/news.release/empsit.nr0.htm"),
}

# card -> (official sources, English query, Korean query, headline must match)
# official source: "fed" | "bea:<release-name regex>" | "treasury:<kind,...>" | "bls:<key>"
CARDS: dict[str, tuple[tuple[str, ...], str, str, str]] = {
    "effr": (("fed",), "Federal Reserve interest rate decision FOMC", "연준 기준금리 FOMC", r"fed|fomc|rate|연준|금리"),
    "fedwatch": (("fed",), "Fed rate cut hike odds FOMC", "연준 금리 인상 인하 전망", r"fed|fomc|rate|연준|금리"),
    "real_policy_rate": (("fed",), "Federal Reserve real interest rate policy", "연준 실질금리", r"fed|rate|연준|금리"),
    "fed_total_assets": (("fed",), "Federal Reserve balance sheet quantitative tightening", "연준 대차대조표 양적긴축", r"balance sheet|qt|quantitative|대차대조표|양적긴축|QT"),
    "fed_ust_holdings": (("fed",), "Federal Reserve Treasury holdings SOMA", "연준 국채 보유 SOMA", r"treasur|soma|balance sheet|국채|대차대조표"),
    "fed_ust_ops": (("fed",), "Federal Reserve Treasury purchases runoff", "연준 국채 매입 축소", r"treasur|purchase|runoff|qt|국채|매입"),
    "bank_reserves": (("fed",), "bank reserves Federal Reserve", "지급준비금 연준", r"reserve|지준|지급준비"),
    "on_rrp": (("fed",), "Fed reverse repo facility usage", "역레포 연준", r"reverse repo|rrp|역레포"),
    "srf_usage": (("fed",), "Fed standing repo facility", "상설레포 연준", r"standing repo|srf|repo|레포"),
    "qra_issuance": (("treasury:refunding,issuance",), "Treasury quarterly refunding", "미 재무부 분기 국채 발행계획", r"refunding|treasury|국채|재무부"),
    "ust_auction_demand": (("treasury:issuance,refunding",), "Treasury auction demand bid to cover", "미국 국채 입찰 수요", r"auction|treasury|입찰|국채"),
    "ust_debt_wam": (("treasury:refunding",), "Treasury bills share debt maturity", "미 재무부 단기채 비중", r"bill|maturit|treasury|단기채|국채"),
    "tga": (("treasury:refunding",), "Treasury General Account cash balance", "미 재무부 일반계정 TGA", r"general account|tga|cash|재무부"),
    "gdp": (("bea:^GDP",), "US GDP BEA estimate", "미국 GDP 성장률", r"gdp|growth|성장"),
    "gdpnow": (("bea:^GDP",), "Atlanta Fed GDPNow", "애틀랜타 연은 GDPNow", r"gdp|성장"),
    "pce_yoy": (("bea:Personal Income and Outlays",), "PCE inflation BEA personal income", "미국 PCE 물가", r"pce|inflation|spending|물가"),
    "core_pce_yoy": (("bea:Personal Income and Outlays",), "core PCE inflation", "미국 근원 PCE", r"pce|inflation|물가"),
    "cpi_yoy": (("bls:cpi",), "US CPI inflation report", "미국 소비자물가 CPI", r"cpi|inflation|consumer price|물가"),
    "core_cpi_yoy": (("bls:cpi",), "US core CPI inflation", "미국 근원 CPI", r"cpi|inflation|물가"),
    "nfp": (("bls:jobs",), "US nonfarm payrolls jobs report", "미국 비농업 고용", r"payroll|jobs|employment|고용"),
    "unemployment": (("bls:jobs",), "US unemployment rate jobs report", "미국 실업률", r"unemployment|jobless|jobs|실업"),
}

# Subjects every country has: the headline must also say it is about the US.
GENERIC = {"cpi_yoy", "core_cpi_yoy", "gdp", "gdpnow", "pce_yoy", "core_pce_yoy", "nfp", "unemployment"}
US_MARK = re.compile(r"\bU\.?S\.?\b|\bUS\b|America|\bFed\b|Federal Reserve|\bBLS\b|\bBEA\b|미국|美|연준", re.I)

EXCLUDE = re.compile(r"bitcoin|crypto|\bcoin\b|token|비트코인|코인|horoscope|lottery", re.I)


def _curl(url: str, timeout: int = 30) -> str:
    proc = subprocess.run(["curl", "-sS", "-L", "-m", str(timeout), "-A", "Mozilla/5.0", url], capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"{url}: curl rc={proc.returncode}")
    return proc.stdout.decode("utf-8", "replace")


def _field(item: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", item, re.S)
    return _html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""


def _date(pub: str) -> str | None:
    try:
        return parsedate_to_datetime(pub).date().isoformat()
    except (TypeError, ValueError):
        return None


def parse_rss(xml: str, source: str) -> list[dict[str, Any]]:
    """Items of an RSS 2.0 feed; `name` is the item's name attribute where a feed uses one (BEA)."""
    out = []
    for attrs, body in re.findall(r"<item([^>]*)>(.*?)</item>", xml, re.S):
        title, link = _field(body, "title"), _field(body, "link")
        if not title or not link:
            continue
        src = _field(body, "source") or source
        if source == "google" and title.endswith(f" - {src}"):
            title = title[: -len(src) - 3].strip()
        name = re.search(r'name="([^"]*)"', attrs)
        out.append({"title": title, "url": link, "source": src, "published_at": _date(_field(body, "pubDate")),
                    "name": name.group(1) if name else None})
    return out


def official_for(card: str, feeds: dict[str, list[dict[str, Any]]], treasury: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for src in CARDS[card][0]:
        kind, _, arg = src.partition(":")
        if kind == "fed":
            out += [{**x, "source": "연준"} for x in feeds.get("fed", [])]
        elif kind == "bea":
            rx = re.compile(arg)
            out += [{**x, "source": "BEA"} for x in feeds.get("bea", []) if x.get("name") and rx.search(x["name"])]
        elif kind == "treasury":
            kinds = set(arg.split(","))
            out += [{"title": x["title"], "url": x["url"], "source": "미 재무부", "published_at": x.get("date")}
                    for x in treasury if x.get("kind") in kinds]
        elif kind == "bls":
            title, url = BLS_LINKS[arg]
            out.append({"title": title, "url": url, "source": "BLS", "published_at": None, "static": True})
    dated = sorted([x for x in out if x.get("published_at")], key=lambda x: x["published_at"], reverse=True)
    static = [x for x in out if not x.get("published_at")]
    return [{k: v for k, v in x.items() if k != "name"} for x in static + dated][:KEEP_OFFICIAL]


def _norm(t: str) -> str:
    return re.sub(r"[\W_]+", "", t).lower()[:40]


def press_for(card: str, google: Callable[[str, str], list[dict[str, Any]]], today: date) -> list[dict[str, Any]]:
    _, en, ko, need = CARDS[card]
    rx = re.compile(need, re.I)
    cutoff = (today - timedelta(days=PRESS_DAYS)).isoformat()
    seen, picked = set(), []
    for lang, q in (("en", en), ("ko", ko)):
        kept = 0
        for x in sorted(google(lang, q), key=lambda x: x.get("published_at") or "", reverse=True):
            k = _norm(x["title"])
            if (k in seen or kept >= KEEP_PRESS // 2 + 1 or not rx.search(x["title"]) or EXCLUDE.search(x["title"])
                    or (card in GENERIC and not US_MARK.search(x["title"])) or (x.get("published_at") or "") < cutoff):
                continue
            seen.add(k)
            picked.append({k2: v for k2, v in x.items() if k2 != "name"} | {"lang": lang})
            kept += 1
    return sorted(picked, key=lambda x: x.get("published_at") or "", reverse=True)[:KEEP_PRESS]


def fetch_feeds() -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    feeds, errors = {}, []
    for key, url in (("fed", FED), ("bea", BEA)):
        try:
            feeds[key] = parse_rss(_curl(url), key)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc}")
    return feeds, errors


def treasury_items() -> list[dict[str, Any]]:
    return json.loads(TREASURY_STORE.read_text(encoding="utf-8")).get("items", []) if TREASURY_STORE.exists() else []


def google_reader(pause: float = 1.0) -> Callable[[str, str], list[dict[str, Any]]]:
    def read(lang: str, q: str) -> list[dict[str, Any]]:
        time.sleep(pause)                                 # a few dozen queries a day; keep them spaced
        return parse_rss(_curl(GNEWS.format(q=quote(q), loc=LOC[lang])), "google")
    return read


def apply(usa: dict, official: dict[str, list], press: dict[str, list]) -> list[str]:
    changed = []
    for ind in usa.get("indicators") or []:
        cid = ind.get("id")
        for key, src in (("news_official", official), ("news_press", press)):
            if cid in src and ind.get(key) != src[cid]:
                ind[key] = src[cid]
                changed.append(f"{cid}.{key}")
    return changed
