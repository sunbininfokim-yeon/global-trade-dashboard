"""US CPI contributions by item: how many percentage points each part of the basket added to headline
and core CPI, month on month and year on year, for every item BLS publishes a weight for.

Inputs, all from BLS:
  * relative importance (www.bls.gov/cpi/tables/relative-importance/<year>.htm) -- each item's share of
    the basket in December of that year, the full item hierarchy (about 320 rows, eight levels);
  * the item catalog (download.bls.gov/pub/time.series/cu/cu.item);
  * the U.S. city-average indexes, from the BLS public data API (api.bls.gov, BLS_API_KEY).
The monthly refresh needs only the API. The weight tables and the catalog are web pages/files, fetched
once a year and kept in config/us_cpi_weights_v1.json; www.bls.gov refuses automated requests that carry
no contact address, so that fetch sends one from BLS_CONTACT_EMAIL (never written to the repo) and is
skipped without it -- the stored tables are used instead.

Method (BLS's own, see "Calculating contributions" in the CPI handbook):
  weight_i(m) = RI_i(Dec) * (I_i(m) / I_i(Dec)) / (I_all(m) / I_all(Dec)),  Dec = the December before m;
  MoM contribution_i(t) = weight_i(t-1) * (I_i(t) / I_i(t-1) - 1)          (seasonally adjusted where BLS
                                                                            publishes it, otherwise not)
  YoY contribution_i(t) = weight_i(t-12) * (I_i(t) / I_i(t-12) - 1)        (not seasonally adjusted)
The year-on-year split crosses one December reweighting, so its parts add up to the published figure only
approximately; the residual is shown. Contributions are computed on the leaves of the hierarchy and summed
upward, so every level adds up. A leaf BLS weights but publishes no index for (mostly "unsampled ..."
residual lines) moves with its nearest parent that has one. Core = all items less food and energy: the
same leaves without the Food subtree, household energy and motor fuel, divided by core's own weight.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
from html.parser import HTMLParser
from typing import Any
from urllib.request import Request, urlopen

RI_URL = "https://www.bls.gov/cpi/tables/relative-importance/{year}.htm"
FILES = "https://download.bls.gov/pub/time.series/cu/{name}"
DATA_FILES = ("cu.data.1.AllItems", "cu.data.11.USFoodBeverage", "cu.data.12.USHousing", "cu.data.13.USApparel",
              "cu.data.14.USTransportation", "cu.data.15.USMedical", "cu.data.16.USRecreation",
              "cu.data.17.USEducationAndCommunication", "cu.data.18.USOtherGoodsAndServices",
              "cu.data.20.USCommoditiesServicesSpecial")
CORE_EXCLUDE = ("Food", "Household energy", "Motor fuel")     # names of subtrees outside core

NAMES_KO = {
    "All items": "전체", "Food and beverages": "식음료", "Food": "식품", "Food at home": "가정식품",
    "Food away from home": "외식", "Alcoholic beverages": "주류", "Housing": "주거", "Shelter": "주거비",
    "Rent of primary residence": "임차료", "Lodging away from home": "숙박", "Owners' equivalent rent of residences": "자가주거비(OER)",
    "Tenants' and household insurance": "세입자·주택 보험", "Fuels and utilities": "연료·공공요금", "Household energy": "가정용 에너지",
    "Water and sewer and trash collection services": "상하수도·쓰레기 수거", "Household furnishings and operations": "가구·가사",
    "Window and floor coverings and other linens": "커튼·카펫·린넨", "Furniture and bedding": "가구·침구", "Appliances": "가전",
    "Other household equipment and furnishings": "기타 가정용품", "Tools, hardware, outdoor equipment and supplies": "공구·철물·야외용품",
    "Housekeeping supplies": "가사용품", "Household operations": "가사 서비스", "Apparel": "의류",
    "Men's and boys' apparel": "남성·남아 의류", "Men's apparel": "남성 의류", "Boys' apparel": "남아 의류",
    "Women's and girls' apparel": "여성·여아 의류", "Women's apparel": "여성 의류", "Girls' apparel": "여아 의류",
    "Footwear": "신발", "Men's footwear": "남성 신발", "Boys' and girls' footwear": "아동 신발", "Women's footwear": "여성 신발",
    "Infants' and toddlers' apparel": "유아 의류", "Jewelry and watches": "보석·시계", "Watches": "시계", "Jewelry": "보석",
    "Transportation": "교통", "Private transportation": "개인 교통", "New and used motor vehicles": "신차·중고차",
    "Motor fuel": "자동차 연료", "Motor vehicle parts and equipment": "자동차 부품·장비",
    "Motor vehicle maintenance and repair": "자동차 정비·수리", "Motor vehicle insurance": "자동차 보험",
    "Motor vehicle fees": "자동차 관련 수수료", "Public transportation": "대중교통", "Airline fares": "항공료",
    "Other intercity transportation": "기타 도시간 교통", "Intracity transportation": "시내 교통",
    "Medical care": "의료", "Medical care commodities": "의료 상품", "Medicinal drugs": "의약품",
    "Medical equipment and supplies": "의료기기·용품", "Medical care services": "의료 서비스",
    "Professional services": "진료비", "Hospital and related services": "병원 서비스", "Health insurance": "건강보험",
    "Recreation": "오락", "Video and audio": "영상·음향", "Televisions": "TV",
    "Cable, satellite, and live streaming television service": "유료방송·스트리밍", "Other video equipment": "기타 영상기기",
    "Purchase, subscription, and rental of video": "영상 구매·구독", "Audio equipment": "음향기기",
    "Recorded music and music subscriptions": "음원·음악 구독", "Pets, pet products and services": "반려동물",
    "Pets and pet products": "반려동물·용품", "Pet services including veterinary": "반려동물 서비스·수의",
    "Sporting goods": "스포츠용품", "Sports vehicles including bicycles": "스포츠 차량·자전거", "Sports equipment": "운동기구",
    "Photography": "사진", "Photographic equipment and supplies": "사진기·용품", "Photographers and photo processing": "사진 서비스",
    "Other recreational goods": "기타 오락용품", "Toys": "장난감", "Sewing machines, fabric and supplies": "재봉용품",
    "Music instruments and accessories": "악기", "Other recreation services": "기타 오락 서비스",
    "Club membership for shopping clubs, fraternal, or other organizations, or participant sports fees": "회원권·스포츠 참가비",
    "Admissions": "입장료", "Fees for lessons or instructions": "강습비", "Recreational reading materials": "읽을거리",
    "Newspapers and magazines": "신문·잡지", "Recreational books": "도서", "Education and communication": "교육·통신",
    "Education": "교육", "Educational books and supplies": "교재·학용품", "Tuition, other school fees, and childcare": "등록금·학비·보육",
    "Communication": "통신", "Postage and delivery services": "우편·택배", "Information and information processing": "정보·정보처리",
    "Telephone services": "전화 서비스", "Information technology, hardware and services": "IT 기기·서비스",
    "Other goods and services": "기타 상품·서비스", "Tobacco and smoking products": "담배", "Cigarettes": "궐련",
    "Tobacco products other than cigarettes": "기타 담배", "Personal care": "개인 관리", "Personal care products": "개인 관리 용품",
    "Personal care services": "미용 서비스", "Miscellaneous personal services": "기타 개인 서비스",
    "Miscellaneous personal goods": "기타 개인 용품", "Electricity": "전기", "Utility (piped) gas service": "도시가스",
    "Fuel oil and other fuels": "난방유 등", "Gasoline (all types)": "휘발유", "New vehicles": "신차",
    "Used cars and trucks": "중고차·트럭", "Car and truck rental": "렌터카", "Prescription drugs": "처방약",
    "Physicians' services": "의사 진료", "Hospital services": "병원", "College tuition and fees": "대학 등록금",
    "Wireless telephone services": "무선통신", "Internet services and electronic information providers": "인터넷",
    "Owners' equivalent rent of primary residence": "자가주거비(주거 주택)",
    "Other lodging away from home including hotels and motels": "호텔·모텔 등 숙박",
    "Unsampled owners' equivalent rent of secondary residences": "별장 자가주거비",
    "Motor vehicle insurance": "자동차 보험", "Full service meals and snacks": "외식(풀서비스)",
    "Limited service meals and snacks": "외식(패스트푸드 등)", "Food at employee sites and schools": "직장·학교 급식",
    "Other food away from home": "기타 외식", "Nonprescription drugs": "일반의약품", "Dental services": "치과",
    "Eyeglasses and eye care": "안경·안과", "Services by other medical professionals": "기타 의료 전문 서비스",
    "Day care and preschool": "보육·유치원", "Elementary and high school tuition and fees": "초중고 학비",
    "Airline fares": "항공료", "Leased cars and trucks": "리스 차량", "Gasoline, unleaded regular": "보통 휘발유",
    "Smartphones": "스마트폰", "Computers, peripherals, and smart home assistants": "컴퓨터·주변기기",
    "Haircuts and other personal care services": "이발·미용", "Household furniture and bedding": "가구·침구",
    "Major appliances": "대형 가전", "Water and sewerage maintenance": "상하수도",
    "Garbage and trash collection": "쓰레기 수거", "Beer, ale, and other malt beverages at home": "맥주(가정)",
    "Distilled spirits at home": "증류주(가정)", "Wine at home": "와인(가정)",
    "Alcoholic beverages away from home": "주류(외식)", "Beef and veal": "소고기", "Pork": "돼지고기",
    "Poultry": "가금류", "Eggs": "계란", "Milk": "우유", "Fresh fruits": "신선 과일", "Fresh vegetables": "신선 채소",
    "Coffee": "커피", "Carbonated drinks": "탄산음료", "Sugar and sweets": "설탕·과자류",
}


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

def user_agent() -> str:
    email = os.environ.get("BLS_CONTACT_EMAIL", "").strip()
    if not email:
        raise RuntimeError("BLS_CONTACT_EMAIL is not set; bls.gov refuses automated requests without a contact")
    return f"global-trade-dashboard macro-monitor (contact: {email})"


def _get(url: str, timeout: int = 180) -> str:
    proc = subprocess.run(["curl", "-sS", "-L", "--fail", "-m", str(timeout), "-A", user_agent(), url],
                          check=False, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{url}: curl rc={proc.returncode}")           # never echo the header back
    return proc.stdout.decode("utf-8", errors="replace")


API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def api_data(series_ids: list[str], start_year: int, end_year: int, key: str | None = None,
             opener=urlopen) -> dict[str, dict[str, float]]:
    """series id -> {YYYY-MM: index} from the BLS API. Ids BLS does not have (many items publish no
    seasonally adjusted index) are left out rather than failing the batch; missing months ("-") too."""
    key = os.environ.get("BLS_API_KEY", "") if key is None else key
    size = 50 if key else 25
    out: dict[str, dict[str, float]] = {}
    for i in range(0, len(series_ids), size):
        payload = {"seriesid": series_ids[i:i + size], "startyear": str(start_year), "endyear": str(end_year)}
        if key:
            payload["registrationkey"] = key
        req = Request(API, data=json.dumps(payload).encode(), method="POST",
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
        with opener(req, timeout=60) as res:
            doc = json.loads(res.read().decode("utf-8"))
        if doc.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS API: {doc.get('status')} {(doc.get('message') or [''])[:1]}")
        for ser in (doc.get("Results") or {}).get("series", []):
            obs = {}
            for row in ser.get("data", []):
                period = str(row.get("period", ""))
                if not period.startswith("M") or period == "M13":
                    continue
                try:
                    obs[f"{row['year']}-{period[1:]}"] = float(row["value"])
                except (KeyError, ValueError):
                    continue
            if obs:
                out.setdefault(ser["seriesID"], {}).update(obs)
    return out


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

class _RiTable(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[list[str], int]] = []
        self._cur: list[str] | None = None
        self._cell: str | None = None
        self._level = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "tr":
            self._cur, self._level = [], 0
        elif tag in ("td", "th") and self._cur is not None:
            self._cell = ""
        elif tag == "p" and self._cell is not None and str(a.get("class") or "").startswith("sub"):
            self._level = int(str(a["class"])[3:] or 0)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cur is not None and self._cell is not None:
            self._cur.append(re.sub(r"\s+", " ", self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._cur:
            self.rows.append((self._cur, self._level))
            self._cur = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell += data


def parse_relative_importance(html: str) -> list[dict[str, Any]]:
    """The item hierarchy with CPI-U December weights, in table order, up to the special aggregates."""
    p = _RiTable()
    p.feed(html)
    out = []
    for cells, level in p.rows:
        if not cells or not cells[0]:
            continue
        if cells[0].startswith("Special aggregate"):
            break
        try:
            ri = float(cells[1])
        except (IndexError, ValueError):
            continue
        out.append({"name": cells[0].rstrip("*").strip(), "level": level, "ri": ri})
    if not out or out[0]["name"] != "All items":
        raise ValueError("relative importance table: no 'All items' row")
    return out


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", name)).strip().lower().rstrip("*")


def parse_items(text: str) -> dict[str, list]:
    """normalised item name -> [item code, display level] (the first listing, the current-base one).
    The catalog's display levels are the hierarchy; the relative-importance page's own indentation is
    not reliable (it puts "Flour" level with "Cereals and cereal products", its parent)."""
    out: dict[str, list] = {}
    for r in csv.DictReader(io.StringIO(text), delimiter="\t"):
        try:
            level = int(r["display_level"])
        except (KeyError, ValueError):
            continue
        out.setdefault(_norm(r["item_name"]), [r["item_code"].strip(), level])
    return out


def parse_data(text: str, keep: set[str]) -> dict[str, dict[str, float]]:
    """series id -> {YYYY-MM: index}, monthly rows only, for the ids in `keep`."""
    out: dict[str, dict[str, float]] = {}
    for line in text.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        sid, year, period = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if sid not in keep or not period.startswith("M") or period == "M13":
            continue
        try:
            out.setdefault(sid, {})[f"{year}-{period[1:]}"] = float(parts[3])
        except ValueError:
            continue
    return out


# --------------------------------------------------------------------------
# Hierarchy and arithmetic
# --------------------------------------------------------------------------

def build_tree(rows: list[dict[str, Any]], items: dict[str, list]) -> list[dict[str, Any]]:
    """Give each weighted row its parent, its item code and a stable id. Depth comes from the BLS catalog
    (All items is the root; the catalog lists the eight groups at its level, so they sit one below). A row
    the catalog lacks (mostly "Unsampled ..." residuals) takes the depth of the nearest row before it that
    the page indents the same and the catalog knows."""
    nodes: list[dict[str, Any]] = []
    stack: list[int] = []
    known_by_page_level: dict[int, int] = {}
    for k, r in enumerate(rows):
        hit = items.get(_norm(r["name"]))
        if k == 0:
            depth = 0
        elif hit:
            depth = hit[1] + 1
            known_by_page_level[r["level"]] = depth
        else:
            depth = known_by_page_level.get(r["level"]) or (known_by_page_level.get(r["level"] - 1, 0) + 1)
        while stack and nodes[stack[-1]]["level"] >= depth:
            stack.pop()
        code = hit[0] if hit else None
        nodes.append({"id": code or f"x{k}", "code": code, "name": r["name"], "name_ko": NAMES_KO.get(r["name"]),
                      "level": depth, "parent": stack[-1] if stack else None, "ri": r["ri"]})
        stack.append(k)
    for n in nodes:
        n["children"] = []
    for k, n in enumerate(nodes):
        if n["parent"] is not None:
            nodes[n["parent"]]["children"].append(k)
    _repair(nodes)
    return nodes


def _gap(nodes: list[dict[str, Any]], k: int) -> float:
    return sum(nodes[c]["ri"] for c in nodes[k]["children"]) - nodes[k]["ri"]


def _repair(nodes: list[dict[str, Any]], tol: float = 0.02) -> None:
    """Weights are additive: a parent's weight is its children's sum. Where the catalog's depth puts a row
    one level off, that fails in a recognisable way -- a parent holding a trailing sibling it should not
    (too heavy), or one missing the siblings that follow it (too light) -- so move those rows until the sums
    hold. Each move must shrink the gap, so this cannot wander."""
    def move(c: int, to: int, at: int | None = None) -> None:
        old = nodes[c]["parent"]
        nodes[old]["children"].remove(c)
        kids = nodes[to]["children"]
        kids.insert(len(kids) if at is None else at, c)
        nodes[c]["parent"] = to

    def pull() -> bool:                                   # too light: take the sibling that follows it
        for k, n in enumerate(nodes):
            if n["children"] and n["parent"] is not None and (g := _gap(nodes, k)) < -tol:
                sibs = nodes[n["parent"]]["children"]
                pos = sibs.index(k)
                if pos + 1 < len(sibs) and abs(g + nodes[sibs[pos + 1]]["ri"]) < -g:
                    move(sibs[pos + 1], k)
                    return True
        return False

    def push() -> bool:                                   # too heavy: hand the last child to the grandparent
        for k, n in enumerate(nodes):
            if n["children"] and n["parent"] is not None and (g := _gap(nodes, k)) > tol:
                last = n["children"][-1]
                if abs(g - nodes[last]["ri"]) < g:
                    gp = n["parent"]
                    move(last, gp, nodes[gp]["children"].index(k) + 1)
                    return True
        return False

    for _ in range(200):                                  # pulls first: a push can strand what a pull needs
        if not (pull() or push()):
            break
    for k, n in enumerate(nodes):                         # depth follows the repaired parents
        d, q = 0, n["parent"]
        while q is not None:
            d, q = d + 1, nodes[q]["parent"]
        n["level"] = d


def tree_gaps(nodes: list[dict[str, Any]], tol: float = 0.02) -> list[str]:
    """Parents whose children's weights do not add up to their own -- a hierarchy mistake."""
    return [f"{n['name']}: {n['ri']} vs {sum(nodes[c]['ri'] for c in n['children']):.3f}"
            for n in nodes if n["children"] and abs(sum(nodes[c]["ri"] for c in n["children"]) - n["ri"]) > tol]


def _prev_month(m: str, n: int = 1) -> str:
    y, mo = int(m[:4]), int(m[5:]) - n
    while mo < 1:
        y, mo = y - 1, mo + 12
    return f"{y:04d}-{mo:02d}"


class Series:
    """Index lookups, with a leaf that has no index of its own following its nearest parent that does."""

    def __init__(self, nodes: list[dict[str, Any]], data: dict[str, dict[str, float]]):
        self.nodes, self.data = nodes, data

    def _own(self, k: int, sa: bool) -> dict[str, float] | None:
        code = self.nodes[k]["code"]
        if not code:
            return None
        return (self.data.get(f"CUSR0000{code}") if sa else None) or self.data.get(f"CUUR0000{code}")

    def index(self, k: int, *, sa: bool, need: tuple[str, ...] = ()) -> dict[str, float] | None:
        """Own index, or the nearest parent's, that has every month in `need` (a series BLS started late,
        or a residual line with no index at all, moves with its group)."""
        while k is not None:
            got = self._own(k, sa)
            if got and all(m in got for m in need):
                return got
            k = self.nodes[k]["parent"]
        return None


def weight(ser: Series, ri_nodes: list[dict[str, Any]], k: int, m: str) -> float | None:
    """Relative importance of node k in month m, carried from the December before m."""
    dec = f"{int(m[:4]) - 1}-12" if m[5:] != "12" else m
    ii, ia = ser.index(k, sa=False, need=(m, dec)), ser.index(0, sa=False, need=(m, dec))
    if not ii or not ia or m not in ii or dec not in ii or m not in ia or dec not in ia:
        return None
    return ri_nodes[k]["ri"] * (ii[m] / ii[dec]) / (ia[m] / ia[dec])


def leaves(nodes: list[dict[str, Any]], root: int = 0, exclude: tuple[str, ...] = ()) -> list[int]:
    out, todo = [], [root]
    while todo:
        k = todo.pop()
        if nodes[k]["name"] in exclude:
            continue
        if nodes[k]["children"]:
            todo.extend(nodes[k]["children"])
        else:
            out.append(k)
    return sorted(out)


def _ri_for(ri_by_year: dict[int, list[dict[str, Any]] | None], m: str) -> list[dict[str, Any]] | None:
    """The December table that weights month m (December m-1, or December m itself for a December)."""
    return ri_by_year.get(int(m[:4]) if m[5:] == "12" else int(m[:4]) - 1)


def _segment(ser: Series, ri_nodes: list[dict[str, Any]], leaf_ids: list[int], s: str, e: str,
             sa: bool) -> tuple[dict[int, float], dict[int, float]]:
    """Per leaf: weight at s and weight x change from s to e (both in RI percent units)."""
    c, w = {}, {}
    for k in leaf_ids:
        idx, wk = ser.index(k, sa=sa, need=(s, e)), weight(ser, ri_nodes, k, s)
        if not idx or wk is None or s not in idx or e not in idx:
            continue
        c[k], w[k] = wk * (idx[e] / idx[s] - 1), wk
    return c, w


def contributions(nodes: list[dict[str, Any]], ri_by_year: dict[int, list[dict[str, Any]] | None],
                  data: dict[str, dict[str, float]], month: str, mode: str,
                  exclude: tuple[str, ...] = ()) -> dict[str, Any] | None:
    """{node index: [change %, contribution pp, weight %]} for every node, plus the sum of the parts.
    Year on year is chained across the December reweighting: with A the part before December and B the
    part after, 1 + Y = (1 + A)(1 + B), so leaf i contributes a_i + (1 + A) b_i and the parts add up."""
    ser = Series(nodes, data)
    sa = mode == "mom"
    base = _prev_month(month, 1 if sa else 12)
    leaf_ids = leaves(nodes, exclude=exclude)
    dec = f"{month[:4]}-12" if month[5:] == "12" else f"{int(month[:4]) - 1}-12"
    cuts = [base, month] if (sa or dec <= base) else [base, dec, month]
    contrib: dict[int, float] = {}
    w0: dict[int, float] = {}
    carried = 1.0                                              # 1 + (part so far), as a fraction
    for s, e in zip(cuts, cuts[1:]):
        ri_nodes = _ri_for(ri_by_year, s)
        if ri_nodes is None:
            return None
        c, w = _segment(ser, ri_nodes, leaf_ids, s, e, sa)
        if not c:
            return None
        tot_w = sum(w.values())                                # each segment in shares of its own basket
        for k, v in c.items():
            contrib[k] = contrib.get(k, 0.0) + carried * v * 100.0 / tot_w
        if not w0:
            w0 = {k: v * 100.0 / tot_w for k, v in w.items()}
        carried *= 1 + sum(c.values()) / tot_w                 # this segment's own change of the basket
    scale = 1.0
    out: dict[int, list[float | None]] = {}

    def change(k: int) -> float | None:
        own = ser._own(k, sa)
        return round((own[month] / own[base] - 1) * 100, 3) if own and month in own and base in own else None

    def fold(k: int) -> tuple[float, float]:
        if nodes[k]["name"] in exclude:
            return 0.0, 0.0
        if not nodes[k]["children"]:
            if k not in contrib:
                return 0.0, 0.0
            out[k] = [change(k), round(contrib[k] * scale, 4), round(w0.get(k, 0.0) * scale, 3)]
            return contrib[k], w0.get(k, 0.0)
        c = ww = 0.0
        for ch in nodes[k]["children"]:
            a, b = fold(ch)
            c, ww = c + a, ww + b
        out[k] = [change(k), round(c * scale, 4), round(ww * scale, 3)]
        return c, ww

    fold(0)
    return {"by_node": out, "sum_pp": round(sum(contrib.values()) * scale, 3)}


def _align(nodes: list[dict[str, Any]], older: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """An older year's weights laid onto this year's tree by item name (BLS renames a few rows a year)."""
    if not older:
        return None
    by = {(_norm(n["name"]), n["level"]): n["ri"] for n in older}
    by_name = {_norm(n["name"]): n["ri"] for n in older}
    return [{**n, "ri": by.get((_norm(n["name"]), n["level"]), by_name.get(_norm(n["name"]), 0.0))} for n in nodes]


def published(data: dict[str, dict[str, float]], code: str, month: str, mode: str) -> float | None:
    sid = f"CUSR0000{code}" if mode == "mom" else f"CUUR0000{code}"
    s = data.get(sid) or {}
    base = _prev_month(month, 1 if mode == "mom" else 12)
    return round((s[month] / s[base] - 1) * 100, 3) if month in s and base in s else None
