"""Contributions to real GDP growth, attached to each country's `gdp` card and drawn by macro.js
(mmContribView): `contrib` is the expenditure side (consumption / investment / government / net
exports), `contrib_industry` the production side where the statistics office publishes it.

Each side is a stacked bar per quarter (WINDOW quarters) with the published growth rate as a dot and
the latest quarter as a table summed against the headline; `detail` (industry side) lists the finer
industries for the latest quarter.

Official contributions as published:
  USA  expenditure  BEA NIPA 1.1.2 via FRED                 pp, annual rate (SAAR)
       industry     BEA GDP by Industry, API TableID 13      pp, annual rate      (needs BEA_API_KEY)
  KOR  both         Bank of Korea ECOS 200Y125 / 200Y123     pp of q/q, s.a.      (needs ECOS_API_KEY)
  JPN  expenditure  Cabinet Office (ESRI) QE kiyo-jk CSV      pp of q/q, s.a.
  CAN  expenditure  Statistics Canada 36-10-0104              pp of q/q, s.a.
  AUS  expenditure  ABS ANA_EXP 'Contributions to growth'     pp of q/q, s.a.
  EMU, CHE          Eurostat namq_10_gdp CON_PPCH_PRE         pp of q/q, s.a.
  IDN  expenditure  BPS 'Source of Growth y-on-y' (var 2129)  pp of y/y           (needs BPS_API_KEY)
Computed here (marked so on the card):
  GBR  expenditure  ONS chained-volume levels: (X_t - X_t-1) / GDP_t-1 -- chain-linking makes the
                    parts not add up exactly; the residual is shown.

Parts add up to the headline only up to rounding, discrepancy and (chain-linked volumes) a residual,
which the table shows rather than hides.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from .us_public_series import Points

WINDOW = 20
FRED = "https://fred.stlouisfed.org/series/{}"
ESTAT = "https://ec.europa.eu/eurostat/databrowser/view/namq_10_gdp/default/table"
_EST = "unit=CON_PPCH_PRE&s_adj=SCA&geo={geo}&na_item={item}"

# A part is (id, Korean label, [(sign, source), ...]) -- the sources are summed with their signs.
Src = tuple
Part = tuple[str, str, list[tuple[int, Src]]]


def _one(src: Src) -> list[tuple[int, Src]]:
    return [(1, src)]


def _eurostat(geo: str) -> dict[str, Any]:
    s = lambda item: ("eurostat", _EST.format(geo=geo, item=item))
    return {
        "basis_ko": "전기 대비 %p (비연율, Eurostat, 계절·영업일조정)",
        "source": "Eurostat namq_10_gdp CON_PPCH_PRE", "source_urls": [ESTAT],
        "total": s("B1GQ"),
        "parts": [("pce", "가계소비", _one(s("P31_S14_S15"))), ("investment", "고정투자", _one(s("P51G"))),
                  ("inventories", "재고", _one(s("P52_P53"))), ("government", "정부", _one(s("P3_S13"))),
                  ("net_exports", "순수출", _one(s("P6X7")))],
    }


def _eurostat_industry(geo: str) -> dict[str, Any]:
    s = lambda n: ("eurostat_a10", f"unit=CON_PPCH_PRE&s_adj=SCA&geo={geo}&na_item=B1G&nace_r2={n}")
    nace = [("A", "농림어업", "other"), ("B-E", "산업(제조·에너지)", "manufacturing"), ("C", "  제조업", "manufacturing"),
            ("F", "건설", "construction"), ("G-I", "유통·운송·숙박", "services"), ("J", "정보통신", "services"),
            ("K", "금융·보험", "services"), ("L", "부동산", "services"), ("M_N", "전문·사업지원", "services"),
            ("O-Q", "공공행정·교육·보건", "services"), ("R-U", "기타 서비스", "services")]
    return {
        "basis_ko": "전기 대비 %p (비연율, Eurostat, 총부가가치 기준)", "source": "Eurostat namq_10_a10 CON_PPCH_PRE",
        "source_urls": ["https://ec.europa.eu/eurostat/databrowser/view/namq_10_a10/default/table"],
        "total_label_ko": "총부가가치 증가율",
        "total": s("TOTAL"),
        "parts": [("manufacturing", "산업(제조·에너지)", _one(s("B-E"))), ("construction", "건설", _one(s("F"))),
                  ("services", "서비스", [(1, s(n)) for n in ("G-I", "J", "K", "L", "M_N", "O-Q", "R-U")]),
                  ("other", "농림어업", _one(s("A")))],
        "detail": [(n, label, g, s(n)) for n, label, g in nace],
        "note_ko": "산업별 기여도는 GDP가 아니라 총부가가치(생산물세 제외) 증가율에 대한 것입니다.",
    }


_ECOS = "https://ecos.bok.or.kr/"
_BEA_IND = "https://www.bea.gov/data/gdp/gdp-industry"
_ONS = "economy/grossdomesticproductgdp/timeseries/{}/qna"
_ONS_HH = "economy/nationalaccounts/satelliteaccounts/timeseries/abjr/qna"

# BEA's 22 industries as in its release chart, with the group each belongs to
BEA_INDUSTRIES = [
    ("11", "농림어업", "goods"), ("21", "광업", "goods"), ("22", "전기·가스·수도", "services"),
    ("23", "건설", "goods"), ("33DG", "내구재 제조", "goods"), ("31ND", "비내구재 제조", "goods"),
    ("42", "도매", "services"), ("44RT", "소매", "services"), ("48TW", "운송·창고", "services"),
    ("51", "정보", "services"), ("52", "금융·보험", "services"), ("53", "부동산·임대", "services"),
    ("54", "전문·과학·기술", "services"), ("55", "기업 관리", "services"), ("56", "사업지원·폐기물", "services"),
    ("61", "교육", "services"), ("62", "보건·사회복지", "services"), ("71", "예술·여가", "services"),
    ("72", "숙박·음식", "services"), ("81", "기타 서비스", "services"), ("GF", "연방정부", "government"),
    ("GSL", "주·지방정부", "government"),
]
KOR_INDUSTRIES = [
    ("1103", "제조업", "manufacturing"), ("110309", "  컴퓨터·전자·광학", "manufacturing"),
    ("110312", "  운송장비", "manufacturing"), ("110305", "  화학", "manufacturing"),
    ("1105", "건설업", "construction"), ("1117", "서비스업", "services"), ("1106", "  도소매·숙박음식", "services"),
    ("1107", "  운수", "services"), ("1108", "  금융·보험", "services"), ("1109", "  부동산", "services"),
    ("1114", "  정보통신", "services"), ("1115", "  사업서비스", "services"),
    ("1112", "  의료·복지", "services"), ("1101", "농림어업", "other"), ("1104", "전기·가스·수도", "other"),
    ("1300", "순생산물세", "taxes"),
]

SIDES: dict[str, dict[str, dict[str, Any]]] = {
    "USA": {
        "expenditure": {
            "basis_ko": "연율 %p (BEA 표 1.1.2, 계절조정)", "source": "BEA NIPA 1.1.2 via FRED",
            "source_urls": ["https://www.bea.gov/data/gdp/gross-domestic-product", FRED.format("A191RL1Q225SBEA")],
            "total": ("fred", "A191RL1Q225SBEA"),
            "parts": [("pce", "민간소비", _one(("fred", "DPCERY2Q224SBEA"))),
                      ("investment", "민간투자(재고 포함)", _one(("fred", "A006RY2Q224SBEA"))),
                      ("government", "정부", _one(("fred", "A822RY2Q224SBEA"))),
                      ("net_exports", "순수출", _one(("fred", "A019RY2Q224SBEA")))],
        },
        "industry": {
            "basis_ko": "연율 %p (BEA 산업별 GDP, 계절조정)", "source": "BEA GDP by Industry (TableID 13)",
            "source_urls": [_BEA_IND], "total": ("bea13", "GDP"),
            "parts": [("goods", "민간 재화산업", _one(("bea13", "PGOOD"))),
                      ("services", "민간 서비스산업", _one(("bea13", "PSERV"))),
                      ("government", "정부", _one(("bea13", "G")))],
            "detail": [(c, label, g, ("bea13", c)) for c, label, g in BEA_INDUSTRIES],
        },
    },
    "KOR": {
        "expenditure": {
            "basis_ko": "전기 대비 %p (비연율, 한국은행, 계절조정)", "source": "한국은행 ECOS 200Y125",
            "source_urls": [_ECOS], "total": ("ecos", "200Y125", "10601"),
            "parts": [("pce", "민간소비", _one(("ecos", "200Y125", "1010110"))),
                      ("construction", "건설투자", _one(("ecos", "200Y125", "1020111"))),
                      ("investment", "설비투자", _one(("ecos", "200Y125", "1020112"))),
                      ("ipp", "지식재산투자", _one(("ecos", "200Y125", "1020113"))),
                      ("inventories", "재고", _one(("ecos", "200Y125", "1020120"))),
                      ("government", "정부소비", _one(("ecos", "200Y125", "1010120"))),
                      ("net_exports", "순수출", _one(("ecos", "200Y125", "1060150")))],
        },
        "industry": {
            "basis_ko": "전기 대비 %p (비연율, 한국은행, 계절조정)", "source": "한국은행 ECOS 200Y123",
            "source_urls": [_ECOS], "total": ("ecos", "200Y123", "1400"),
            "parts": [("manufacturing", "제조업", _one(("ecos", "200Y123", "1103"))),
                      ("services", "서비스업", _one(("ecos", "200Y123", "1117"))),
                      ("construction", "건설업", _one(("ecos", "200Y123", "1105"))),
                      ("other", "농림어업·전기가스", [(1, ("ecos", "200Y123", "1101")), (1, ("ecos", "200Y123", "1102")),
                                                (1, ("ecos", "200Y123", "1104"))]),
                      ("taxes", "순생산물세", _one(("ecos", "200Y123", "1300")))],
            "detail": [(c, label, g, ("ecos", "200Y123", c)) for c, label, g in KOR_INDUSTRIES],
        },
    },
    "JPN": {
        "expenditure": {
            "basis_ko": "전기 대비 %p (비연율, 내각부, 계절조정)", "source": "내각부 경제사회종합연구소 QE 기여도",
            "source_urls": ["https://www.esri.cao.go.jp/jp/sna/sokuhou/sokuhou_top.html"], "total": ("esri", 1),
            "parts": [("pce", "민간소비", _one(("esri", 2))),
                      ("investment", "주택·설비투자", [(1, ("esri", 5)), (1, ("esri", 6))]),
                      ("inventories", "재고(민간·공적)", [(1, ("esri", 7)), (1, ("esri", 10))]),
                      ("government", "정부(소비·공공투자)", [(1, ("esri", 8)), (1, ("esri", 9))]),
                      ("net_exports", "순수출", _one(("esri", 11)))],
        },
    },
    "CAN": {
        "expenditure": {
            "basis_ko": "전기 대비 %p (비연율, 캐나다 통계청, 계절조정)", "source": "Statistics Canada 36-10-0104",
            "source_urls": ["https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610010401"], "total": ("statcan", 30),
            "parts": [("pce", "가계소비", [(1, ("statcan", 2)), (1, ("statcan", 8))]),
                      ("investment", "기업투자", _one(("statcan", 11))),
                      ("inventories", "재고", _one(("statcan", 19))),
                      ("government", "정부(소비·투자)", [(1, ("statcan", 9)), (1, ("statcan", 18))]),
                      ("net_exports", "순수출", [(1, ("statcan", 23)), (-1, ("statcan", 26))])],
        },
    },
    "AUS": {
        "expenditure": {
            "basis_ko": "전기 대비 %p (비연율, ABS, 계절조정, 소수 1자리)", "source": "ABS ANA_EXP Contributions to growth",
            "source_urls": ["https://www.abs.gov.au/statistics/economy/national-accounts"],
            "total": ("absagg", "M2.GPM.20.AUS.Q"),
            "parts": [("pce", "가계소비", _one(("abs", "TCH.FCE.PHS.20.AUS.Q"))),
                      ("investment", "민간투자", _one(("abs", "TCH.GFC.PSS.20.AUS.Q"))),
                      ("inventories", "재고", _one(("abs", "TCH.IST.SSS.20.AUS.Q"))),
                      ("government", "정부(소비·투자)", [(1, ("abs", "TCH.FCE.GGS.20.AUS.Q")), (1, ("abs", "TCH.GFC.GSS.20.AUS.Q"))]),
                      ("net_exports", "순수출", [(1, ("abs", "TCH.XGS.SSS.20.AUS.Q")), (1, ("abs", "TCH.MGS.SSS.20.AUS.Q"))])],
            "note_ko": "ABS는 수입 기여도를 음수로 발표합니다. 통계상 불일치는 잔차에 들어갑니다.",
        },
    },
    "SGP": {
        "expenditure": {
            "basis_ko": "전년 동기 대비 %p (SingStat 실질값으로 계산)", "source": "SingStat M014811 (computed)",
            "source_urls": ["https://tablebuilder.singstat.gov.sg/table/TS/M014811"], "computed_from_levels": True, "lag": 4,
            "total": ("singstat", "M014811", "1"),
            "parts": [("pce", "민간소비", _one(("singstat", "M014811", "1.1.1"))),
                      ("investment", "고정투자", _one(("singstat", "M014811", "1.2.1"))),
                      ("inventories", "재고", _one(("singstat", "M014811", "1.2.2"))),
                      ("government", "정부소비", _one(("singstat", "M014811", "1.1.2"))),
                      ("net_exports", "순수출", _one(("singstat", "M014811", "1.5")))],
            "note_ko": "SingStat은 지출항목 기여도를 따로 내지 않아, 실질(연쇄) 수준값으로 (항목의 전년 동기 대비 변화 ÷ 전년 동기 GDP)를 계산했습니다. 통계상 불일치·연쇄가중 차이는 잔차로 표시합니다.",
        },
        "industry": {
            "basis_ko": "전년 동기 대비 %p (SingStat, 원계열)", "source": "SingStat M015671",
            "source_urls": ["https://tablebuilder.singstat.gov.sg/table/TS/M015671"], "total": ("singstat", "M015671", "1"),
            "parts": [("goods", "재화산업", _one(("singstat", "M015671", "1.1"))),
                      ("services", "서비스산업", _one(("singstat", "M015671", "1.2"))),
                      ("other", "주거소유", _one(("singstat", "M015671", "1.3"))),
                      ("taxes", "생산물세", _one(("singstat", "M015671", "1.4")))],
            "detail": [(r, label, g, ("singstat", "M015671", r)) for r, label, g in [
                ("1.1.1", "제조업", "goods"), ("1.1.2", "  건설", "goods"), ("1.2.1", "도소매", "services"),
                ("1.2.2", "  운수·창고", "services"), ("1.2.3", "  숙박·음식", "services"), ("1.2.4", "  정보통신", "services"),
                ("1.2.5", "  금융·보험", "services"), ("1.2.6", "  부동산·전문·사업지원", "services"),
                ("1.2.7", "  기타 서비스", "services")]],
        },
    },
    "HKG": {
        "expenditure": {
            "basis_ko": "전년 동기 대비 %p (홍콩 정부통계처, 원계열)", "source": "C&SD 310-31004",
            "source_urls": ["https://www.censtatd.gov.hk/en/web_table.html?id=310-31004"], "total": ("csd", "310-31004", ""),
            "parts": [("pce", "민간소비", _one(("csd", "310-31004", "PCE"))),
                      ("investment", "고정투자", _one(("csd", "310-31004", "GDFCF"))),
                      ("inventories", "재고", _one(("csd", "310-31004", "CIV"))),
                      ("government", "정부소비", _one(("csd", "310-31004", "GCE"))),
                      ("net_exports", "순수출", [(1, ("csd", "310-31004", c)) for c in ("XG", "XS", "MG", "MS")])],
            "note_ko": "홍콩은 재수출 비중이 커서 상품 수출·수입 기여도가 각각 ±50%p에 이르고, 순수출은 그 차이입니다.",
        },
    },
    "ISR": {
        "expenditure": {
            "basis_ko": "전기 대비 %p (비연율, 이스라엘은행 실질값으로 계산)", "source": "Bank of Israel NA (computed)",
            "source_urls": ["https://www.boi.org.il/en/economic-roles/statistics/"], "computed_from_levels": True,
            "total": ("boi", "NA", "GDP_Q_FP_SA"),
            "parts": [("pce", "민간소비", _one(("boi", "NA", "C_Q_FP_SA"))),
                      ("investment", "투자", _one(("boi", "NA", "I_Q_FP_SA"))),
                      ("government", "정부소비", _one(("boi", "NA", "G_Q_FP_SA"))),
                      ("net_exports", "순수출", [(1, ("boi", "NA", "X_Q_FP_SA")), (-1, ("boi", "NA", "M_NO_TAX_Q_FP_SA"))])],
            "note_ko": "이스라엘은행은 기여도 계열을 내지 않아, 실질 계절조정 수준값으로 (항목 변화 ÷ 전기 GDP)를 계산했습니다. "
                       "재고 계열이 없어 재고·연쇄가중 차이는 잔차에 들어갑니다. 수입은 BOI 'M_NO_TAX' 계열입니다.",
        },
    },
    "BRA": {
        "expenditure": {
            "basis_ko": "전기 대비 %p (비연율, IBGE 계절조정 실질 증가율 × 전기 명목 비중으로 계산)", "source": "IBGE SIDRA 6613 + 1846 (computed)",
            "source_urls": ["https://sidra.ibge.gov.br/tabela/6613", "https://sidra.ibge.gov.br/tabela/1846"],
            "share_weighted": True, "nominal_kind": "sidra_nom",
            "total": ("sidra", "90707"),
            "parts": [("pce", "가계소비", _one(("sidra", "93404"))),
                      ("investment", "고정투자", _one(("sidra", "93406"))),
                      ("government", "정부소비", _one(("sidra", "93405"))),
                      ("net_exports", "순수출", [(1, ("sidra", "93407")), (-1, ("sidra", "93408"))])],
            "note_ko": "IBGE는 기여도 계열을 내지 않아 (전기 명목 비중 × 계절조정 실질 증가율)로 계산했습니다. 재고는 계절조정 실질계열이 없고, IBGE가 항목별로 따로 계절조정해 합이 맞지 않으므로 잔차가 큰 분기가 있습니다(표의 잔차 행).",
        },
        "industry": {
            "basis_ko": "전기 대비 %p (비연율, IBGE 실질 증가율 × 전기 명목 비중으로 계산)", "source": "IBGE SIDRA 6613 + 1846 (computed)",
            "source_urls": ["https://sidra.ibge.gov.br/tabela/6613", "https://sidra.ibge.gov.br/tabela/1846"],
            "share_weighted": True, "nominal_kind": "sidra_nom",
            "total": ("sidra", "90707"),
            "parts": [("other", "농축산업", _one(("sidra", "90687"))),
                      ("manufacturing", "산업(광업·제조·전기·건설)", _one(("sidra", "90691"))),
                      ("services", "서비스업", _one(("sidra", "90696")))],
            "note_ko": "부가가치 기준 계산값입니다. 생산물세(순)는 계절조정 계열이 없어 잔차에 들어갑니다.",
        },
    },
    "EMU": {"expenditure": _eurostat("EA"), "industry": _eurostat_industry("EA")},
    "CHE": {"expenditure": {**_eurostat("CH"), "note_ko": "스위스 순수출은 금·의약품 교역 때문에 분기마다 크게 흔들립니다."},
            "industry": _eurostat_industry("CH")},
    "IDN": {
        "expenditure": {
            "basis_ko": "전년 동기 대비 %p (BPS 성장 원천, 원계열)", "source": "BPS Source of Growth y-on-y (var 2129)",
            "source_urls": ["https://www.bps.go.id/en/subject/11/gross-domestic-product--expenditure-.html"],
            "total": ("bps", 800),
            "parts": [("pce", "가계소비", [(1, ("bps", 100)), (1, ("bps", 200))]),
                      ("investment", "고정투자", _one(("bps", 400))),
                      ("government", "정부", _one(("bps", 300))),
                      ("net_exports", "순수출", [(1, ("bps", 600)), (-1, ("bps", 700))])],
            "note_ko": "BPS는 분기 전기비를 계절조정하지 않아 전년 동기 대비 성장 원천을 씁니다. 재고·통계상 불일치는 잔차에 들어갑니다.",
        },
    },
    "GBR": {
        "expenditure": {
            "basis_ko": "전기 대비 %p (비연율, ONS 실질값으로 계산)", "source": "ONS QNA chained volume (computed)",
            "source_urls": ["https://www.ons.gov.uk/economy/grossdomesticproductgdp"], "computed_from_levels": True,
            "total": ("ons", _ONS.format("abmi")),
            "parts": [("pce", "가계소비", [(1, ("ons", _ONS_HH)), (1, ("ons", _ONS.format("hayo")))]),
                      ("investment", "고정투자", _one(("ons", _ONS.format("npqt")))),
                      ("inventories", "재고", _one(("ons", _ONS.format("cafu")))),
                      ("government", "정부", _one(("ons", _ONS.format("nmry")))),
                      ("net_exports", "순수출", [(1, ("ons", _ONS.format("ikbk"))), (-1, ("ons", _ONS.format("ikbl")))])],
            "note_ko": "ONS는 지출항목 기여도를 별도 계열로 내지 않아, 실질(연쇄) 수준값으로 (항목 변화 ÷ 전기 GDP)를 계산했습니다. "
                       "연쇄가중 때문에 합이 정확히 맞지 않고 그 차이는 잔차로 표시합니다.",
        },
    },
}
COUNTRIES = {iso: sides["expenditure"] for iso, sides in SIDES.items() if "expenditure" in sides}   # back-compat


# --------------------------------------------------------------------------
# Readers (keys from the environment, else ~/.config/<name>.env -- never logged)
# --------------------------------------------------------------------------

def _key(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    if v:
        return v
    f = Path.home() / ".config" / f"{name.split('_')[0].lower()}.env"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return None


class Readers:
    """Each `kind` returns ascending (ISO quarter-start date, value) points; responses are cached."""

    def __init__(self, fetch=None, get=None):
        from .world_public_series import Fetch, _get
        self.fetch = fetch or Fetch()
        self._get = get or _get
        self._cache: dict[Any, Any] = {}

    def __call__(self, src: Src) -> Points:
        if src not in self._cache:
            self._cache[src] = getattr(self, "_" + src[0])(*src[1:])
        return self._cache[src]

    def _fred(self, sid):
        return self.fetch.get("fred", sid)

    def _eurostat(self, query):
        return self.fetch.get("eurostat", "namq_10_gdp", query)

    def _eurostat_a10(self, query):
        return self.fetch.get("eurostat", "namq_10_a10", query)

    def _statcan(self, est):
        import urllib.request
        body = json.dumps([{"productId": 36100104, "coordinate": f"1.3.1.{est}.0.0.0.0.0.0", "latestN": 60}]).encode()
        doc = json.loads(self._get("https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods",
                                   data=body, headers={"Content-Type": "application/json"}))[0]
        return sorted((p["refPer"], float(p["value"])) for p in doc["object"]["vectorDataPoint"] if p.get("value") is not None)

    def _abs(self, key):
        from .world_public_series import period_key
        text = self._get(f"https://data.api.abs.gov.au/rest/data/ABS,ANA_EXP,1.0.0/{key}?startPeriod=2010-Q1&format=csvfile").decode()
        return sorted((period_key(r["TIME_PERIOD"]), float(r["OBS_VALUE"])) for r in csv.DictReader(io.StringIO(text)) if r["OBS_VALUE"])

    def _absagg(self, key):
        from .world_public_series import period_key
        text = self._get(f"https://data.api.abs.gov.au/rest/data/ABS,ANA_AGG,1.0.0/{key}?startPeriod=2010-Q1&format=csvfile").decode()
        return sorted((period_key(r["TIME_PERIOD"]), float(r["OBS_VALUE"])) for r in csv.DictReader(io.StringIO(text)) if r["OBS_VALUE"])

    def _ons(self, path):
        return self.fetch.get("ons", path)

    def _ecos(self, table, item):
        key = _key("ECOS_API_KEY")
        if not key:
            raise RuntimeError("no ECOS_API_KEY")
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/1000/{table}/Q/2010Q1/2030Q4/{item}"
        try:
            doc = json.loads(self._get(url))
        except Exception as exc:  # noqa: BLE001 -- never let the URL (it holds the key) into a message
            raise RuntimeError(f"ECOS {table}/{item}: {type(exc).__name__}") from None
        rows = (doc.get("StatisticSearch") or {}).get("row") or []
        if not rows:
            raise RuntimeError(f"ECOS {table}/{item}: {(doc.get('RESULT') or {}).get('CODE', 'no rows')}")
        return sorted((f"{r['TIME'][:4]}-{(int(r['TIME'][5]) - 1) * 3 + 1:02d}-01", float(r["DATA_VALUE"])) for r in rows)

    def _singstat(self, table, row):
        from . import sg_public_series as sgs
        pts, _ = sgs.fetch_row(table, row)
        return pts

    def _boi(self, flow, code):
        return self.fetch.get("boi", flow, code)

    def _csd(self, table, component):
        """Hong Kong C&SD table API; quarters are labelled by their last month (202606 = 2026Q2)."""
        if ("csd", table) not in self._cache:
            self._cache[("csd", table)] = json.loads(self._get(
                f"https://www.censtatd.gov.hk/api/get.php?id={table}&lang=en&full_series=1"))["dataSet"]
        out = []
        for r in self._cache[("csd", table)]:
            if r.get("freq") != "Q" or r.get("GDP_COMPONENT", "") != component or r.get("figure") in (None, ""):
                continue
            y, m = r["period"][:4], int(r["period"][4:6])
            out.append((f"{y}-{m - 2:02d}-01", float(r["figure"])))
        return sorted(out)

    def _sidra(self, cat):
        return self.fetch.get("sidra", f"t/6613/n1/all/v/9319/p/last%2060/c11255/{cat}")

    def _sidra_nom(self, cat):
        return self.fetch.get("sidra", f"t/1846/n1/all/v/585/p/last%2060/c11255/{cat}")

    def _bea13(self, industry):
        if ("bea13_all",) not in self._cache:
            key = _key("BEA_API_KEY")
            if not key:
                raise RuntimeError("no BEA_API_KEY")
            from datetime import date
            years = ",".join(str(y) for y in range(date.today().year - 5, date.today().year + 1))
            url = (f"https://apps.bea.gov/api/data?UserID={key}&method=GetData&datasetname=GDPbyIndustry&TableID=13"
                   f"&Frequency=Q&Year={years}&Industry=ALL&ResultFormat=JSON")
            try:
                doc = json.loads(self._get(url, timeout=180))
            except Exception as exc:  # noqa: BLE001 -- the URL holds the key
                raise RuntimeError(f"BEA TableID 13: {type(exc).__name__}") from None
            res = doc["BEAAPI"]["Results"]
            res = res[0] if isinstance(res, list) else res
            if "Error" in res:
                raise RuntimeError(f"BEA TableID 13: {res['Error'].get('APIErrorDescription')}")
            q = {"I": 1, "II": 4, "III": 7, "IV": 10}
            by: dict[str, list] = {}
            for r in res["Data"]:
                try:
                    by.setdefault(r["Industry"], []).append((f"{r['Year']}-{q[r['Quarter']]:02d}-01", float(r["DataValue"])))
                except (KeyError, ValueError):
                    continue
            self._cache[("bea13_all",)] = {k: sorted(v) for k, v in by.items()}
        pts = self._cache[("bea13_all",)].get(industry)
        if not pts:
            raise ValueError(f"BEA TableID 13: no {industry}")
        return pts

    def _esri(self, col):
        if ("esri_rows",) not in self._cache:
            top = self._get("https://www.esri.cao.go.jp/jp/sna/sokuhou/sokuhou_top.html").decode("utf-8", "replace")
            menu = re.search(r'href="(/jp/sna/data/data_list/sokuhou/files/\d{4}/qe\d+_\d+/gdemenuja\.html)"', top)
            if not menu:
                raise ValueError("ESRI: latest QE menu not found")
            base = "https://www.esri.cao.go.jp" + menu.group(1).rsplit("/", 1)[0] + "/"
            page = self._get(base + "gdemenuja.html").decode("utf-8", "replace")
            csvname = re.search(r'href="(tables/kiyo-jk\d+\.csv)"', page)
            if not csvname:
                raise ValueError("ESRI: kiyo-jk CSV not found")
            text = self._get(base + csvname.group(1)).decode("shift_jis", "replace")
            rows, year = {}, None
            months = {"1- 3.": 1, "4- 6.": 4, "7- 9.": 7, "10-12.": 10}
            for row in csv.reader(io.StringIO(text)):
                if not row or not row[0].strip():
                    continue
                label = row[0].strip()
                m = re.match(r"(\d{4})/\s*(.*)$", label)
                if m:
                    year, label = int(m.group(1)), m.group(2).strip()
                if year is None or label not in months:
                    continue
                rows[f"{year:04d}-{months[label]:02d}-01"] = row
            self._cache[("esri_rows",)] = rows
        out = []
        for d, row in sorted(self._cache[("esri_rows",)].items()):
            try:
                out.append((d, float(row[col])))
            except (IndexError, ValueError):
                continue
        return out

    def _bps(self, region):
        from . import idn_public_series as idn
        key = idn.api_key()
        if not key:
            raise RuntimeError("no BPS_API_KEY")
        if ("bps2129",) not in self._cache:
            from datetime import date
            docs = [idn._get_json(2129, th, key) for th in idn.year_chunks(date.today().year - 6, date.today().year)]
            self._cache[("bps2129",)] = docs
        pts: dict[str, float] = {}
        for doc in self._cache[("bps2129",)]:
            if doc.get("data-availability") == "available":
                pts.update(idn.parse_bps(doc, 2129, region, idn.QUARTERS))
        return sorted(pts.items())


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

def _quarter(d: str) -> str:
    return f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"


def _sum(read: Callable[[Src], Points], terms: list[tuple[int, Src]]) -> dict[str, float]:
    series = [(sign, dict(read(src))) for sign, src in terms]
    common = set.intersection(*(set(s) for _, s in series))
    return {d: sum(sign * s[d] for sign, s in series) for d in common}


def _from_levels(levels: dict[str, float], gdp: dict[str, float], lag: int = 1) -> dict[str, float]:
    """Contribution of a chained-volume component: its change over the base period's GDP, in pp
    (lag 1 = on the previous quarter, lag 4 = on the same quarter a year earlier)."""
    ds = sorted(levels)
    return {d: (levels[d] - levels[p]) / gdp[p] * 100 for p, d in zip(ds, ds[lag:]) if p in gdp}


def build_side(spec: dict[str, Any], read: Callable[[Src], Points]) -> dict[str, Any]:
    total = dict(read(spec["total"]))
    if spec.get("share_weighted"):
        # contribution = last quarter's nominal share x this quarter's real growth (chained volumes in an
        # old base year -- IBGE's 1995 prices -- would weight the parts by a 30-year-old price structure)
        real_gdp = total
        ds = sorted(real_gdp)
        total = {d: (real_gdp[d] / real_gdp[p] - 1) * 100 for p, d in zip(ds, ds[1:])}
        nom_gdp = dict(read((spec["nominal_kind"], spec["total"][1])))
        parts = []
        for pid, label, terms in spec["parts"]:
            acc: dict[str, float] = {}
            ok: set[str] | None = None
            for sign, src in terms:
                real, nom = dict(read(src)), dict(read((spec["nominal_kind"], src[1])))
                rd = sorted(real)
                term = {d: sign * nom[p] / nom_gdp[p] * (real[d] / real[p] - 1) * 100
                        for p, d in zip(rd, rd[1:]) if p in nom and p in nom_gdp and real[p]}
                ok = set(term) if ok is None else ok & set(term)
                for d, v in term.items():
                    acc[d] = acc.get(d, 0.0) + v
            parts.append((pid, label, {d: acc[d] for d in (ok or set())}))
    elif spec.get("computed_from_levels"):
        gdp, lag = total, spec.get("lag", 1)
        ds = sorted(gdp)
        total = {d: (gdp[d] / gdp[p] - 1) * 100 for p, d in zip(ds, ds[lag:])}
        parts = [(pid, label, _from_levels(_sum(read, terms), gdp, lag)) for pid, label, terms in spec["parts"]]
    else:
        parts = [(pid, label, _sum(read, terms)) for pid, label, terms in spec["parts"]]
    dates = sorted(d for d in total if all(d in p for _, _, p in parts))[-WINDOW:]
    if not dates:
        raise ValueError("no quarter with every component")
    last = dates[-1]
    out_parts = [{"id": pid, "label_ko": label, "values": [round(p[d], 2) for d in dates]} for pid, label, p in parts]
    s = sum(p["values"][-1] for p in out_parts)
    side = {
        "basis_ko": spec["basis_ko"], "source": spec["source"], "source_urls": spec["source_urls"],
        "note_ko": spec.get("note_ko"), "total_label_ko": spec.get("total_label_ko"), "computed": bool(spec.get("computed_from_levels") or spec.get("share_weighted")),
        "periods": [_quarter(d) for d in dates], "dates": dates,
        "total": [round(total[d], 2) for d in dates], "parts": out_parts,
        "latest": {"period": _quarter(last), "total": round(total[last], 2), "sum_parts": round(s, 2),
                   "residual": round(total[last] - s, 2)},
    }
    if spec.get("detail"):
        rows = []
        for did, label, group, src in spec["detail"]:
            try:
                v = dict(read(src)).get(last)
            except Exception:  # noqa: BLE001 -- a missing detail row is left out, not fatal
                v = None
            if v is not None:
                rows.append({"id": did, "label_ko": label, "group": group, "value": round(v, 2)})
        side["detail"] = rows
    return side


def build(iso3: str, read: Callable[[str, str], Points] | Callable[[Src], Points], side: str = "expenditure") -> dict[str, Any]:
    """`read(src)` (or, for the original two-argument form, `read(kind, key)`) returns the points."""
    spec = SIDES[iso3][side]
    try:
        import inspect
        two_arg = len(inspect.signature(read).parameters) == 2
    except (TypeError, ValueError):
        two_arg = False
    reader = (lambda src: read(*src)) if two_arg else read
    return build_side(spec, reader)


def apply(country: dict[str, Any], contrib: dict[str, Any] | None, industry: dict[str, Any] | None = None) -> bool:
    """Attach to the `gdp` card. The card's old `components` list was a seeded fixture (round numbers
    with no source); with an observed breakdown in hand it goes."""
    gdp = next((i for i in country.get("indicators") or [] if i.get("id") == "gdp"), None)
    if gdp is None:
        return False
    changed = False
    if contrib is not None and gdp.get("contrib") != contrib:
        gdp["contrib"] = contrib
        changed = True
    if industry is not None and gdp.get("contrib_industry") != industry:
        gdp["contrib_industry"] = industry
        changed = True
    if (contrib is not None or industry is not None) and gdp.pop("components", None) is not None:
        changed = True
    return changed
