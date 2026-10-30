"""Item-level CPI movers outside the US: the same "항목별" panel the U.S. CPI card has.

Each country lists a curated set of published CPI sub-indices (groups and a few headline-moving
items), read from the statistics office or central bank that publishes them:

  KOR  Bank of Korea ECOS 901Y009 (by purpose) and 901Y010 (by product type) -- needs ECOS_API_KEY
  JPN  Statistics Bureau of Japan, national CPI CSV (2025 base, every item in one file) -- keyless
  EMU  Eurostat prc_hicp_minr (HICP, ECOICOP ver. 2, index 2025=100) -- keyless
  GBR  ONS MM23 CPI division indices -- keyless
  CAN  Statistics Canada 18-10-0004-01 vectors -- keyless
  BRA  IBGE SIDRA table 7060 (IPCA by item: monthly and 12-month rates as published) -- keyless

The ranking is the same as the U.S. one: each item's own month-on-month change, not its
weighted contribution to the headline. Indices are not seasonally adjusted, so a seasonal
item (cabbage, airfares) can top the list in its season; the note on the panel says so.

Every value is a published index or rate, or arithmetic on one. An item that cannot be read
keeps the observations the snapshot already has; nothing is estimated.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import world_public_series as wps

Points = list[tuple[str, float]]

SNAPSHOT = Path(__file__).resolve().parent.parent / "config" / "cpi_items_v1.json"
KEEP_MONTHS = 30                       # enough for a year-on-year on the latest month plus history slack

JP_STAT_CSV = "https://www.stat.go.jp/data/cpi/2025/csv/zmi2025aa.csv"


# --------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------

def parse_jp_stat_items(text: str, codes: tuple[str, ...]) -> dict[str, Points]:
    """The national CPI CSV: row 0 Japanese names, row 1 English names, row 2 item codes, rows 3-5
    serial/weights, then one row per month (YYYYMM, then an index per item)."""
    rows = list(csv.reader(io.StringIO(text)))
    head = next(i for i, r in enumerate(rows) if r and r[0].startswith("類・品目符号"))
    col = {c.strip(): i for i, c in enumerate(rows[head]) if c.strip()}
    out: dict[str, Points] = {c: [] for c in codes}
    for r in rows[head + 1:]:
        ym = (r[0] if r else "").strip()
        if len(ym) != 6 or not ym.isdigit():
            continue
        for c in codes:
            i = col.get(c)
            if i is None or i >= len(r) or not r[i].strip():
                continue
            try:
                out[c].append((f"{ym[:4]}-{ym[4:]}-01", float(r[i])))
            except ValueError:
                pass
    return {c: sorted(p) for c, p in out.items()}


class Readers:
    """One instance per run: each upstream file or series is read once."""

    def __init__(self, *, ecos_series: Callable[..., Any] | None = None, http: Callable[[str], bytes] | None = None,
                 fetch: wps.Fetch | None = None):
        self._ecos_series = ecos_series
        self._http = http or (lambda url: wps._get(url))
        self.f = fetch or wps.Fetch()
        self._jp: dict[str, Points] | None = None

    def ecos(self, stat: str, code: str) -> Points:
        if self._ecos_series is None:
            from . import ecos
            self._ecos_series = ecos.series
        pts, _unit = self._ecos_series(stat, "M", (code,))
        return pts

    def jp(self, code: str) -> Points:
        if self._jp is None:
            raw = self._http(JP_STAT_CSV)
            text = raw.decode("cp932", errors="replace") if isinstance(raw, bytes) else raw
            self._jp = parse_jp_stat_items(text, JP_CODES)
        return self._jp.get(code) or []

    def eurostat(self, coicop: str) -> Points:
        return self.f.get("eurostat", "prc_hicp_minr", f"unit=I25&geo=EA&coicop18={coicop}")

    def ons(self, cdid: str) -> Points:
        return self.f.get("ons", f"economy/inflationandpriceindices/timeseries/{cdid}/mm23")

    def statcan(self, vector: int) -> Points:
        return [(d[:7] + "-01", v) for d, v in self.f.get("statcan", vector)]

    def sidra(self, variable: int, code: str) -> Points:
        return self.f.get("sidra", f"t/7060/n1/all/v/{variable}/p/last%2030/c315/{code}")


# --------------------------------------------------------------------------
# Country item lists
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    id: str
    label_ko: str
    read: Callable[[Readers], Any]


@dataclass(frozen=True)
class Country:
    iso3: str
    targets: tuple[str, ...]           # indicator ids the movers attach to
    publisher_ko: str
    source: str
    urls: tuple[str, ...]
    items: tuple[Item, ...]
    kind: str = "index"                # "index": read levels; "rates": read {"mom", "yoy"} as published


def _ecos(stat: str, code: str) -> Callable[[Readers], Points]:
    return lambda r: r.ecos(stat, code)


def _jp(code: str) -> Callable[[Readers], Points]:
    return lambda r: r.jp(code)


def _eu(code: str) -> Callable[[Readers], Points]:
    return lambda r: r.eurostat(code)


def _ons(cdid: str) -> Callable[[Readers], Points]:
    return lambda r: r.ons(cdid)


def _sc(vector: int) -> Callable[[Readers], Points]:
    return lambda r: r.statcan(vector)


def _ipca(code: str) -> Callable[[Readers], dict[str, Points]]:
    return lambda r: {"mom": r.sidra(63, code), "yoy": r.sidra(2265, code)}


KOR = Country("KOR", ("cpi_yoy", "core_cpi_yoy"), "통계청(한국은행 ECOS)", "ecos:901Y009+901Y010",
              ("https://ecos.bok.or.kr/",), (
    Item("agri", "농축수산물", _ecos("901Y010", "211")),
    Item("processed_food", "가공식품", _ecos("901Y010", "2121")),
    Item("durables", "내구재", _ecos("901Y010", "2122")),
    Item("petroleum", "석유류", _ecos("901Y010", "2125")),
    Item("pharma", "의약품", _ecos("901Y010", "2126")),
    Item("utilities", "전기·가스·수도", _ecos("901Y010", "213")),
    Item("rent", "집세", _ecos("901Y010", "221")),
    Item("public_services", "공공서비스", _ecos("901Y010", "222")),
    Item("eating_out", "외식", _ecos("901Y010", "2231")),
    Item("personal_services_x_eating", "외식 제외 개인서비스", _ecos("901Y010", "2239")),
    Item("jeonse", "전세", _ecos("901Y009", "D01101")),
    Item("wolse", "월세", _ecos("901Y009", "D01102")),
    Item("electricity", "전기료", _ecos("901Y009", "D05101")),
    Item("city_gas", "도시가스", _ecos("901Y009", "D05201")),
    Item("gasoline", "휘발유", _ecos("901Y009", "G02101")),
    Item("diesel", "경유", _ecos("901Y009", "G02102")),
    Item("intl_airfare", "국제항공료", _ecos("901Y009", "G03302")),
    Item("mobile_phone", "휴대전화료", _ecos("901Y009", "H03102")),
    Item("rice", "쌀", _ecos("901Y009", "A01101")),
    Item("pork", "돼지고기", _ecos("901Y009", "A01203")),
    Item("apple", "사과", _ecos("901Y009", "A01601")),
    Item("cabbage", "배추", _ecos("901Y009", "A01701")),
    Item("insurance", "보험서비스료", _ecos("901Y009", "L03104")),
    Item("education", "교육", _ecos("901Y009", "J")),
))

# (id, label, item code in the CSV)
JP_ITEMS = (
    ("fresh_food", "신선식품", "0157"),
    ("food_x_fresh", "신선식품 제외 식료품", "0172"),
    ("rice", "쌀", "0004"),
    ("meats", "육류", "0013"),
    ("fresh_vegetables", "신선 채소", "0022"),
    ("cakes_candies", "과자류", "0033"),
    ("eating_out", "외식", "0043"),
    ("private_rent", "민간 집세", "0047"),
    ("electricity", "전기료", "0056"),
    ("gas", "가스료", "0057"),
    ("gasoline", "휘발유", "7301"),
    ("household_durables", "가정용 내구재", "0061"),
    ("clothing", "의류", "0083"),
    ("medical_care", "보건의료", "0107"),
    ("public_transport", "공공교통", "0112"),
    ("automobiles", "자동차", "0114"),
    ("communication", "통신", "0117"),
    ("school_fees", "수업료", "0119"),
    ("hotel", "숙박료", "0139"),
    ("package_tours", "패키지 여행", "0177"),
    ("tobacco", "담배", "0155"),
    ("energy", "에너지", "0167"),
    ("services_x_rent", "서비스(귀속 집세 제외)", "0242"),
)
JP_CODES = tuple(code for _, _, code in JP_ITEMS)
JPN = Country("JPN", ("core_cpi_jp", "core_core_cpi"), "総務省統計局", "stat.go.jp:zmi2025aa",
              ("https://www.stat.go.jp/data/cpi/",), tuple(Item(i, label, _jp(code)) for i, label, code in JP_ITEMS))

EMU = Country("EMU", ("hicp_yoy", "core_hicp_yoy"), "Eurostat", "eurostat:prc_hicp_minr",
              ("https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_minr/default/table",), (
    Item("food", "식품", _eu("CP011")),
    Item("unprocessed_food", "비가공 식품", _eu("FOOD_NP")),
    Item("processed_food", "가공 식품(주류·담배 포함)", _eu("FOOD_P")),
    Item("alcohol_tobacco", "주류·담배", _eu("CP02")),
    Item("clothing", "의류·신발", _eu("CP03")),
    Item("rent", "실제 임차료", _eu("CP041")),
    Item("electricity_gas", "전기·가스·연료", _eu("CP045")),
    Item("energy", "에너지", _eu("NRG")),
    Item("fuels", "운송용 연료", _eu("FUEL")),
    Item("furnishings", "가구·가사용품", _eu("CP05")),
    Item("health", "보건", _eu("CP06")),
    Item("vehicles", "차량 구입", _eu("CP071")),
    Item("transport_services", "여객 운송 서비스", _eu("CP073")),
    Item("communication", "정보·통신", _eu("CP08")),
    Item("package_holidays", "패키지 여행", _eu("CP098")),
    Item("recreation", "오락·스포츠·문화", _eu("CP09")),
    Item("education", "교육", _eu("CP10")),
    Item("restaurants", "음식점", _eu("CP111")),
    Item("accommodation", "숙박", _eu("CP112")),
    Item("insurance_financial", "보험·금융", _eu("CP12")),
    Item("neig", "비에너지 공업제품", _eu("IGD_NNRG")),
    Item("services", "서비스", _eu("SERV")),
))

GBR = Country("GBR", ("cpi_yoy", "core_cpi_yoy"), "ONS", "ons:mm23",
              ("https://www.ons.gov.uk/economy/inflationandpriceindices",), (
    Item("food_bev", "식료품·비주류음료", _ons("d7bu")),
    Item("food", "식품", _ons("d7c8")),
    Item("alcohol_tobacco", "주류·담배", _ons("d7bv")),
    Item("clothing", "의류·신발", _ons("d7bw")),
    Item("housing", "주거·수도·연료", _ons("d7bx")),
    Item("furnishings", "가구·가사용품", _ons("d7by")),
    Item("health", "보건", _ons("d7bz")),
    Item("transport", "교통", _ons("d7c2")),
    Item("communication", "통신", _ons("d7c3")),
    Item("recreation", "오락·문화", _ons("d7c4")),
    Item("education", "교육", _ons("d7c5")),
    Item("restaurants_hotels", "음식점·숙박", _ons("d7c6")),
    Item("misc", "기타 상품·서비스", _ons("d7c7")),
    Item("energy", "에너지", _ons("dk9t")),
))

CAN = Country("CAN", ("cpi_yoy",), "Statistics Canada", "statcan:18-10-0004-01",
              ("https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401",), (
    Item("food", "식품", _sc(41690974)),
    Item("food_stores", "매장 구입 식품", _sc(41690975)),
    Item("shelter", "주거", _sc(41691050)),
    Item("owned_accommodation", "자가 주거", _sc(41691055)),
    Item("household_ops", "가사 운영·가구·장비", _sc(41691067)),
    Item("clothing", "의류·신발", _sc(41691108)),
    Item("transportation", "교통", _sc(41691128)),
    Item("health_personal", "보건·개인관리", _sc(41691153)),
    Item("recreation", "오락·교육·독서", _sc(41691170)),
    Item("alcohol_tobacco", "주류·담배·대마", _sc(41691206)),
    Item("energy", "에너지", _sc(41691239)),
    Item("services", "서비스", _sc(41691230)),
))

BRA = Country("BRA", ("ipca",), "IBGE", "sidra:7060",
              ("https://sidra.ibge.gov.br/tabela/7060",), (
    Item("food_bev", "식품·음료", _ipca("7170")),
    Item("food_home", "가정 내 식품", _ipca("7171")),
    Item("meats", "육류", _ipca("7283")),
    Item("food_away", "외식", _ipca("7432")),
    Item("housing", "주거", _ipca("7445")),
    Item("rent", "주택 임차료", _ipca("7448")),
    Item("bottled_gas", "가스(LPG 통)", _ipca("7482")),
    Item("electricity", "주거용 전기료", _ipca("7484")),
    Item("household_articles", "가정용품", _ipca("7486")),
    Item("apparel", "의류", _ipca("7558")),
    Item("transport", "교통", _ipca("7625")),
    Item("airfare", "항공료", _ipca("7634")),
    Item("new_cars", "신차", _ipca("7641")),
    Item("gasoline", "휘발유", _ipca("7657")),
    Item("diesel", "경유", _ipca("7659")),
    Item("health", "보건·개인관리", _ipca("7660")),
    Item("health_plans", "건강보험료", _ipca("7695")),
    Item("personal_expenses", "개인 지출", _ipca("7712")),
    Item("education", "교육", _ipca("7766")),
    Item("communication", "통신", _ipca("7786")),
), kind="rates")

COUNTRIES: dict[str, Country] = {c.iso3: c for c in (KOR, JPN, EMU, GBR, CAN, BRA)}


# --------------------------------------------------------------------------
# Rates and movers
# --------------------------------------------------------------------------

def _shift(d: str, months: int) -> str:
    y, m = int(d[:4]), int(d[5:7]) - months
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}-01"


def rates_from_index(points: Points) -> dict[str, dict[str, float]]:
    """Month -> {"mom": %, "yoy": %} from an index level series (a rate needs both ends)."""
    by = dict(points)
    out: dict[str, dict[str, float]] = {}
    for d, v in points:
        row: dict[str, float] = {}
        prev, year_ago = by.get(_shift(d, 1)), by.get(_shift(d, 12))
        if prev:
            row["mom"] = (v / prev - 1) * 100
        if year_ago:
            row["yoy"] = (v / year_ago - 1) * 100
        if row:
            out[d] = row
    return out


def rates_published(mom: Points, yoy: Points) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for d, v in mom:
        out.setdefault(d, {})["mom"] = v
    for d, v in yoy:
        out.setdefault(d, {})["yoy"] = v
    return out


def item_rates(country: Country, stored: dict[str, Any]) -> dict[str, dict[str, dict[str, float]]]:
    out = {}
    for it in country.items:
        s = stored.get(it.id)
        if not s:
            continue
        if country.kind == "rates":
            out[it.id] = rates_published([tuple(p) for p in s.get("mom", [])], [tuple(p) for p in s.get("yoy", [])])
        else:
            out[it.id] = rates_from_index([tuple(p) for p in s])
    return out


def latest_month(rates: dict[str, dict[str, dict[str, float]]], min_items: int) -> str | None:
    """The newest month at least `min_items` items have a MoM for (a late item does not hold the panel back,
    and one early item does not move it forward)."""
    counts: dict[str, int] = {}
    for by_month in rates.values():
        for d, r in by_month.items():
            if "mom" in r:
                counts[d] = counts.get(d, 0) + 1
    ok = [d for d, n in counts.items() if n >= min_items]
    return max(ok) if ok else None


def movers(country: Country, stored: dict[str, Any], *, top: int = 3) -> dict[str, Any] | None:
    rates = item_rates(country, stored)
    month = latest_month(rates, max(3, (len(country.items) * 2 + 2) // 3))
    if not month:
        return None
    labels = {it.id: it.label_ko for it in country.items}
    rows = []
    for it in country.items:
        r = rates.get(it.id, {}).get(month)
        if not r or "mom" not in r:
            continue
        rows.append({"id": it.id, "label_ko": labels[it.id], "mom_pct": round(r["mom"], 3),
                     "yoy_pct": None if r.get("yoy") is None else round(r["yoy"], 3)})
    rows.sort(key=lambda r: r["mom_pct"], reverse=True)
    if len(rows) < 2 * top:
        return None
    return {
        "reference_period": month[:7],
        "basis": "item_mom_percent_change_unweighted",
        "items_ranked": len(rows),
        "source": country.source,
        "source_urls": list(country.urls),
        "note_ko": (f"{country.publisher_ko} 공표 하위 지수 {len(rows)}개의 전월비 순위입니다. "
                    "가중치를 곱한 헤드라인 기여도가 아니고, 계절조정 전 지수라 제철 품목이 상위에 올 수 있습니다."),
        "up": rows[:top],
        "down": rows[-top:][::-1],
    }


# --------------------------------------------------------------------------
# Snapshot: collect, keep what could not be read, attach
# --------------------------------------------------------------------------

def _tail(points: Points) -> list[list[Any]]:
    return [[d, round(v, 4)] for d, v in sorted(points)[-KEEP_MONTHS:]]


def collect(country: Country, readers: Readers, previous: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Read every item; an item that fails keeps its stored observations. Returns (items, errors)."""
    items = dict(previous)
    errors = []
    for it in country.items:
        try:
            got = it.read(readers)
            if country.kind == "rates":
                if not got["mom"]:
                    raise ValueError("no observations")
                items[it.id] = {"mom": _tail(got["mom"]), "yoy": _tail(got["yoy"])}
            else:
                if not got:
                    raise ValueError("no observations")
                items[it.id] = _tail(got)
        except Exception as exc:  # noqa: BLE001 -- one item must not sink the country
            errors.append(f"{it.id}: {type(exc).__name__}: {str(exc)[:120]}")
    return items, errors


def load_snapshot(path: Path = SNAPSHOT) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": "cpi-items-v1", "countries": {}}


def save_snapshot(doc: dict[str, Any], path: Path = SNAPSHOT) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def attach(pack: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, str]:
    """Put each country's movers on its CPI indicators. Returns iso3 -> reference month (or reason)."""
    done = {}
    for c in pack.get("countries", []):
        country = COUNTRIES.get(c.get("iso3"))
        if not country:
            continue
        stored = (snapshot.get("countries", {}).get(country.iso3) or {}).get("items") or {}
        mv = movers(country, stored)
        if not mv:
            done[country.iso3] = "no movers"
            continue
        hit = False
        for ind in c.get("indicators", []):
            if ind.get("id") in country.targets:
                ind["movers"] = mv
                hit = True
        done[country.iso3] = mv["reference_period"] if hit else "no target indicator"
    return done
