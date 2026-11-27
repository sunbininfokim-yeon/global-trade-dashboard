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

# Official pages for sources with no free feed (or one that refuses automated readers): linked, never fetched.
LINKS = {
    "h41": ("연준 H.4.1 대차대조표 — 최신", "https://www.federalreserve.gov/releases/h41/"),
    "h6": ("연준 H.6 통화량(M2) — 최신", "https://www.federalreserve.gov/releases/h6/"),
    "h8": ("연준 H.8 은행 자산·부채 — 최신", "https://www.federalreserve.gov/releases/h8/"),
    "g17": ("연준 G.17 산업생산·가동률 — 최신", "https://www.federalreserve.gov/releases/g17/"),
    "g19": ("연준 G.19 소비자신용 — 최신", "https://www.federalreserve.gov/releases/g19/"),
    "chargeoff": ("연준 대출 연체율·상각률 통계 — 최신", "https://www.federalreserve.gov/releases/chargeoff/"),
    "sloos": ("연준 고위대출담당자 설문(SLOOS) — 최신", "https://www.federalreserve.gov/data/sloos.htm"),
    "z1": ("연준 Z.1 금융계정 — 최신", "https://www.federalreserve.gov/releases/z1/"),
    "sofr": ("뉴욕연준 SOFR — 최신", "https://www.newyorkfed.org/markets/reference-rates/sofr"),
    "fima": ("뉴욕연준 FIMA 레포 창구", "https://www.newyorkfed.org/markets/fima-repo-facility"),
    "yield": ("미 재무부 일별 국채 금리 — 최신", "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"),
    "real_yield": ("미 재무부 일별 실질 금리(TIPS) — 최신", "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_real_yield_curve"),
    "buyback": ("미 재무부 바이백 결과 — 최신", "https://www.treasurydirect.gov/auctions/buybacks/"),
    "debt": ("미 재무부 Debt to the Penny — 최신", "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/"),
    "mts": ("미 재무부 월간 재정보고서(MTS) — 최신", "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/"),
    "fdic_qbp": ("FDIC 분기 은행 보고서(QBP) — 최신", "https://www.fdic.gov/quarterly-banking-profile"),
    "claims": ("미 노동부 주간 실업수당 청구 — 최신", "https://www.dol.gov/ui/data.pdf"),
    "eia_elec": ("EIA 전력 월보 — 최신", "https://www.eia.gov/electricity/monthly/"),
    "cleveland": ("클리블랜드 연은 절사평균 CPI — 최신", "https://www.clevelandfed.org/indicators-and-data/median-cpi"),
    "mxp": ("BLS 수출입물가 보도자료 — 최신", "https://www.bls.gov/news.release/ximpim.nr0.htm"),
    "pmms": ("프레디맥 주간 모기지 금리(PMMS) — 최신", "https://www.freddiemac.com/pmms"),
    "case_shiller": ("S&P 케이스-실러 주택가격지수 — 최신", "https://www.spglobal.com/spdji/en/index-family/indicators/sp-corelogic-case-shiller/"),
    "census_c30": ("센서스 건설 지출 — 최신", "https://www.census.gov/construction/c30/current/index.html"),
    "fred_hy": ("ICE BofA 하이일드 OAS (FRED) — 최신", "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"),
    "fred_sahm": ("Sahm 규칙 실시간 지표 (FRED) — 최신", "https://fred.stlouisfed.org/series/SAHMREALTIME"),
    "fred_bei": ("10년 기대인플레이션 BEI (FRED) — 최신", "https://fred.stlouisfed.org/series/T10YIE"),
}

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
    # liquidity
    "net_liquidity": (("fed", "link:h41"), "Fed liquidity reserves TGA reverse repo", "연준 유동성 지준 TGA", r"liquidity|reserve|tga|repo|유동성|지준"),
    "hedge_fund_ust": (("link:z1",), "hedge funds Treasury basis trade", "헤지펀드 국채 베이시스 트레이드", r"hedge fund|basis trade|헤지펀드|베이시스"),
    "fima_repo": (("link:fima",), "Fed FIMA repo facility foreign central banks dollars", "연준 FIMA 레포 달러", r"fima|repo|dollar|레포|달러"),
    "m2_vs_2019": (("link:h6",), "US M2 money supply", "미국 M2 통화량", r"m2|money supply|통화량"),
    "m2_yoy": (("link:h6",), "US M2 money supply growth", "미국 M2 증가율", r"m2|money supply|통화량"),
    "ust_buybacks": (("treasury:buyback", "link:buyback"), "Treasury buyback", "미 재무부 국채 바이백", r"buyback|바이백|환매"),
    "npl_noncurrent": (("link:fdic_qbp",), "FDIC banks noncurrent loans", "미국 은행 부실채권 FDIC", r"fdic|noncurrent|bank|loan|부실|은행"),
    "delinq_all": (("link:chargeoff",), "US bank loan delinquency charge-offs", "미국 은행 대출 연체율", r"delinquen|charge-off|loan|연체|상각"),
    # rates
    "sofr": (("link:sofr", "fed"), "SOFR secured overnight financing rate", "SOFR 금리", r"sofr|repo|funding|레포"),
    "sofr_iorb": (("link:sofr", "fed"), "SOFR IORB spread repo funding pressure", "SOFR 지준부리 레포 금리", r"sofr|ioer|iorb|repo|funding|레포"),
    "bond_3m": (("link:yield",), "Treasury bill yields", "미국 단기국채 금리", r"bill|treasur|yield|국채|금리"),
    "bond_2y": (("link:yield",), "2-year Treasury yield", "미국 2년물 국채 금리", r"2-year|two-year|treasur|yield|2년물"),
    "bond_10y": (("link:yield",), "10-year Treasury yield", "미국 10년물 국채 금리", r"10-year|ten-year|treasur|yield|10년물"),
    "tips_10y": (("link:real_yield",), "TIPS real yields", "미국 실질금리 TIPS", r"tips|real yield|실질금리"),
    "spread_10y3m": (("link:yield",), "yield curve inversion 10-year 3-month", "미국 장단기 금리차 역전", r"yield curve|inver|spread|커브|금리차|역전"),
    "spread_10y2y": (("link:yield",), "yield curve 2s10s steepening", "미국 장단기 금리차 2년 10년", r"yield curve|2s10s|steep|spread|커브|금리차"),
    "sovereign_debt": (("link:debt", "treasury:refunding"), "US national debt", "미국 국가부채", r"debt|deficit|부채|적자"),
    "sovereign_interest": (("link:mts",), "US interest costs on federal debt", "미국 국채 이자 비용", r"interest|debt|이자|부채"),
    "hy_oas": (("link:fred_hy",), "high yield bond spreads junk", "하이일드 채권 스프레드", r"high.yield|junk|spread|credit|하이일드|스프레드"),
    "sovereign_ratings": ((), "US credit rating Moody's S&P Fitch", "미국 신용등급", r"rating|moody|fitch|s&p|신용등급"),
    # fx / equity
    "dxy": ((), "dollar index DXY", "달러인덱스", r"dollar|dxy|달러"),
    "eurusd": ((), "euro dollar EUR/USD", "유로 달러 환율", r"euro|eur|유로"),
    "usdjpy": ((), "dollar yen USD/JPY", "엔달러 환율", r"yen|jpy|엔"),
    "spx": ((), "S&P 500 stocks", "S&P500 지수", r"s&p|stocks|wall street|증시|S&P"),
    "ndx": ((), "Nasdaq 100 tech stocks", "나스닥 지수", r"nasdaq|tech|나스닥"),
    "rut": ((), "Russell 2000 small caps", "러셀2000 소형주", r"russell|small.cap|러셀|소형주"),
    "vix": ((), "VIX volatility index", "VIX 변동성 지수", r"vix|volatil|변동성|공포"),
    # growth
    "electricity_generation": (("link:eia_elec",), "US electricity demand power generation data centers", "미국 전력 수요 발전량", r"electric|power|grid|전력|발전"),
    "sahm": (("link:fred_sahm", "bls:jobs"), "Sahm rule recession indicator", "샴의 법칙 경기침체", r"sahm|recession|샴|침체"),
    "initial_claims": (("link:claims",), "US initial jobless claims", "미국 신규 실업수당 청구", r"jobless|claims|실업수당"),
    "auto_loans": (("link:g19",), "US auto loans consumer credit", "미국 자동차 대출", r"auto loan|car loan|consumer credit|자동차 대출|소비자신용"),
    "ip_semis": (("link:g17",), "US semiconductor production chips factory output", "미국 반도체 생산", r"semiconductor|chip|industrial production|반도체|산업생산"),
    "cu_manufacturing": (("link:g17",), "US capacity utilization manufacturing output", "미국 제조업 가동률", r"capacity utilization|manufactur|industrial production|가동률|제조업"),
    # inflation
    "trimmed_mean_cpi": (("link:cleveland", "bls:cpi"), "Cleveland Fed trimmed mean median CPI", "클리블랜드 연은 절사평균 CPI", r"trimmed|median|cpi|inflation|물가"),
    "export_price_yoy": (("link:mxp",), "US export prices", "미국 수출물가", r"export price|import price|수출물가"),
    "import_price_yoy": (("link:mxp",), "US import prices tariffs", "미국 수입물가", r"import price|수입물가"),
    "bei_10y": (("link:fred_bei",), "breakeven inflation expectations TIPS", "기대인플레이션 BEI", r"breakeven|inflation expectation|기대인플레"),
    # real estate
    "mortgage_30y": (("link:pmms",), "30-year mortgage rate Freddie Mac", "미국 모기지 금리", r"mortgage|모기지"),
    "mortgage_spread": (("link:pmms",), "mortgage rate spread Treasury MBS", "모기지 금리 스프레드 MBS", r"mortgage|mbs|spread|모기지"),
    "home_price_yoy": (("link:case_shiller",), "Case-Shiller US home prices", "미국 집값 케이스실러", r"home price|house price|case-shiller|집값|주택가격"),
    "price_to_rent": (("link:case_shiller",), "US home prices rents affordability", "미국 집값 임대료", r"home price|rent|afford|집값|임대료"),
    "bank_cre_loans": (("link:h8",), "commercial real estate loans banks", "상업용 부동산 대출 은행", r"commercial real estate|cre|office|상업용 부동산"),
    "sloos_cre": (("link:sloos",), "senior loan officer survey lending standards commercial real estate", "연준 대출 태도 설문 상업용 부동산", r"loan officer|lending standard|cre|commercial real estate|대출"),
    "sloos_mortgage_demand": (("link:sloos",), "mortgage demand loan officer survey", "주택담보대출 수요", r"mortgage|loan officer|demand|주택담보|모기지"),
    "industrial_capex": (("link:census_c30", "bea:^GDP"), "data center construction spending capex", "데이터센터 건설 투자", r"data center|construction|capex|factory|데이터센터|설비투자|건설"),
}

# Subjects every country has: the headline must also say it is about the US.
GENERIC = {"cpi_yoy", "core_cpi_yoy", "gdp", "gdpnow", "pce_yoy", "core_pce_yoy", "nfp", "unemployment",
           "m2_vs_2019", "m2_yoy", "bond_3m", "bond_2y", "bond_10y", "spread_10y3m", "spread_10y2y", "sovereign_debt",
           "sovereign_interest", "sovereign_ratings", "initial_claims", "electricity_generation", "auto_loans", "ip_semis",
           "cu_manufacturing", "trimmed_mean_cpi", "export_price_yoy", "import_price_yoy", "mortgage_30y", "home_price_yoy",
           "price_to_rent", "bank_cre_loans", "industrial_capex", "npl_noncurrent", "delinq_all"}
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
        elif kind == "link":
            title, url = LINKS[arg]
            out.append({"title": title, "url": url, "source": "공식", "published_at": None, "static": True})
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
