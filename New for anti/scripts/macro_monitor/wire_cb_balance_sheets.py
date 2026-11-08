#!/usr/bin/env python3
"""Asset/liability stacks for five central banks, drawn the way the Fed card draws its balance sheet.

    python3 wire_cb_balance_sheets.py              # all five
    python3 wire_cb_balance_sheets.py --only KOR,JPN

Each bank's card gets a `balance_sheet` block (macro_monitor/cb_balance.py), which macro.js shows as the
부채 / 자산 tabs. Sources, all public and keyless except ECOS (ECOS_API_KEY, already used by the Korea
pipeline):

  KOR  한국은행 주요계정 (ECOS 103Y002), month-end, 십억원          -> bok_total_assets
  JPN  Bank of Japan Accounts (BOJ stat-search BS01), month-end, 1억엔 -> boj_total_assets
  EMU  Eurosystem weekly financial statement (ECB ILM), €mn          -> ecb_total_assets
  GBR  Bank of England weekly series (IADB RPWB*), £mn               -> boe_total_assets (was a demo card)
  CHN  货币当局资产负债表 (PBoC 调查统计司, yearly HTML tables), 亿元  -> pboc_total_assets (new card)

A bank that cannot be read keeps what the pack has; the others still update. Exit 1 if any failed.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import cb_balance as cb  # noqa: E402
from macro_monitor import ecos  # noqa: E402
from macro_monitor import jp_public_series as jps  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402
from macro_monitor import world_public_series as wps  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
Points = cb.Points

# One palette for every bank so the same kind of line keeps its colour from card to card:
# reserves orange, currency blue, government deposits sky, securities cyan/violet, lending green.
C = {"reserves": "#f97316", "currency": "#3b82f6", "gov": "#38bdf8", "sterilise": "#a78bfa", "repo": "#e879f9",
     "other_l": "#22c55e", "bonds": "#0ea5e9", "bonds2": "#8b5cf6", "lending": "#10b981", "fx": "#f59e0b",
     "gold": "#eab308", "etf": "#ec4899", "other_a": "#64748b"}

OTHER_L = {"id": "other", "label_ko": "기타 부채·자본", "color": C["other_l"],
           "note_ko": "총액에서 위 항목들을 뺀 나머지(자본금, 충당금, 재평가 계정, 기타 예금 등). 잔차로 계산했습니다."}
OTHER_A = {"id": "other_assets", "label_ko": "기타 자산", "color": C["other_a"],
           "note_ko": "총액에서 위 항목들을 뺀 나머지. 잔차로 계산했습니다."}


def L(id_: str, label: str, color: str, note: str) -> dict[str, str]:
    return {"id": id_, "label_ko": label, "color": color, "note_ko": note}


# --------------------------------------------------------------------------
# Bank of Korea
# --------------------------------------------------------------------------

def korea() -> dict[str, Any]:
    def s(item: str) -> Points:
        pts, _ = ecos.series("103Y002", "M", (item,))
        return [(ups.month_end(d), v * 1e-3) for d, v in pts]         # 십억원 -> 조원
    assets = [
        L("foreign_sec", "외국증권", C["fx"], "외환보유액을 운용하는 해외 채권·주식. 한은 자산의 가장 큰 부분입니다."),
        L("fx_dep", "외화예치금", C["gold"], "해외 은행에 맡긴 외화 예금(외환보유액의 일부)."),
        L("domestic_sec", "국내 유가증권", C["bonds"], "한은이 보유한 국채 등 원화 증권. 단순매입·RP 담보와 별개입니다."),
        L("loans", "대출금", C["lending"], "금융중개지원대출 등 은행에 빌려준 돈."),
        L("rp_bought", "RP 매입", C["repo"], "환매조건부채권 매입 -- 시장에 유동성을 넣은 잔액."),
        L("other_foreign", "기타 대외자산", "#fde68a", "IMF 출자금·SDR·금 등 외국증권·외화예치금 밖의 국외자산(국외자산 합계에서 차감)."),
    ]
    liabilities = [
        L("currency", "화폐발행", C["currency"], "시중에 풀린 지폐·동전."),
        L("reserves", "지급준비예금", C["reserves"], "은행이 한은에 맡긴 지준. 시중 유동성이 실제로 쓰이는 부분입니다."),
        L("msb", "통화안정증권", C["sterilise"], "외환을 사들이며 풀린 원화를 거둬들이려 발행한 한은 채권(불태화)."),
        L("msa", "통화안정계정", "#c4b5fd", "은행 자금을 기간부로 예치받아 흡수하는 계정(2010년 신설)."),
        L("rp_sold", "RP 매각", C["repo"], "환매조건부채권 매각 -- 시장 유동성을 흡수한 잔액."),
        L("gov", "중앙정부예금", C["gov"], "정부가 한은에 둔 돈. 늘면 그만큼 시중에서 빠집니다."),
        L("other_dep", "기타 예금", "#fdba74", "예금 합계에서 지준예금·정부예금을 뺀 나머지(비은행 금융기관 예금 등)."),
        L("other_dom", "기타 국내부채", "#86efac", "은행의 외화 예치금 등 기타 국내부채."),
        L("foreign_liab", "국외부채", "#fcd34d", "SDR 배분액·비거주자 예금 등 해외에 진 부채."),
        L("capital", "자본", "#94a3b8", "한은 자본금과 적립금."),
    ]
    codes = {"foreign_sec": "BCAA122", "fx_dep": "BCAA123", "domestic_sec": "BCAA113", "loans": "BCAA112",
             "rp_bought": "BCAA117", "currency": "BCAA211", "reserves": "BCAA2121", "msb": "BCAA215",
             "msa": "BCAA220", "rp_sold": "BCAA216", "gov": "BCAA213"}
    codes |= {"other_dom": "BCAA219", "foreign_liab": "BCAA22", "capital": "BCAA3", "_deposits": "BCAA212",
              "_foreign": "BCAA12"}
    series = {k: s(c) for k, c in codes.items()}

    def minus(base: str, *parts: str) -> Points:
        ms = [dict(series[p]) for p in parts]
        return [(d, v - sum(m[d] for m in ms)) for d, v in series[base] if all(d in m for m in ms)]
    series["other_dep"] = minus("_deposits", "reserves", "gov")
    series["other_foreign"] = minus("_foreign", "foreign_sec", "fx_dep")
    return cb.block(total=s("BCAA1"), assets=assets, liabilities=liabilities, series=series,
                    asset_residual=OTHER_A, liability_residual=OTHER_L, since="2015-01-01", meta={
                        "source": "한국은행 ECOS 103Y002(한국은행 주요계정), 월말 잔액",
                        "source_urls": ["https://ecos.bok.or.kr/"], "frequency": "monthly", "unit": "tn_krw",
                        "unit_suffix": "조원", "data_status": "live",
                        "liabilities_note_ko": "발행한 돈이 어디에 머물러 있는가.",
                        "assets_note_ko": "한은이 무엇을 들고 있는가 -- 대부분 외환보유액입니다.",
                        "stack_note_ko": ("한은 자산의 대부분은 외환보유액(외국증권·외화예치금)이고, 그 대가로 풀린 원화의 상당 "
                                          "부분을 통화안정증권으로 다시 흡수합니다(불태화). 그래서 지급준비예금보다 통안증권이 "
                                          "더 큽니다 -- 연준과 정반대 구조입니다."),
                    })


# --------------------------------------------------------------------------
# Bank of Japan
# --------------------------------------------------------------------------

def japan() -> dict[str, Any]:
    def s(code: str) -> Points:
        return [(ups.month_end(d), v * 1e-4) for d, v in jps.fetch_boj("BS01", code, start="201501")]  # 1억엔 -> 조엔
    assets = [
        L("jgb", "국채(JGB)", C["bonds"], "일본은행이 보유한 장기 국채. 2024년 정책 전환 뒤 매입을 줄이며 감소 중입니다."),
        L("tbills", "단기국채(T-bill)", C["bonds2"], "재무성 단기증권."),
        L("etf", "ETF(신탁)", C["etf"], "주가지수 ETF 보유분(장부가)."),
        L("loans", "대출", C["lending"], "공통담보 자금공급 등 은행 대출."),
        L("fx", "외화자산", C["fx"], "외화 표시 자산."),
    ]
    liabilities = [
        L("reserves", "당좌예금", C["reserves"], "은행이 일본은행에 맡긴 당좌예금(지준). 양적완화로 불어난 부분입니다."),
        L("currency", "은행권", C["currency"], "발행 은행권."),
        L("gov", "정부예금", C["gov"], "정부가 일본은행에 둔 예금."),
        L("repo", "매현조건부 채무", C["repo"], "환매조건부 채권 매도에 따른 부채."),
    ]
    codes = {"jgb": "MABJMA5B", "tbills": "MABJMA5A", "etf": "MABJMA003", "loans": "MABJMA@01", "fx": "MABJMA12",
             "reserves": "MABJML11", "currency": "MABJML1", "gov": "MABJML3", "repo": "MABJML8"}
    series = {k: s(c) for k, c in codes.items()}
    return cb.block(total=s("MABJMTA"), assets=assets, liabilities=liabilities, series=series,
                    asset_residual=OTHER_A, liability_residual=OTHER_L, since="2015-01-01", meta={
                        "source": "일본은행 시계열 통계 BS01(Bank of Japan Accounts), 월말 잔액",
                        "source_urls": ["https://www.stat-search.boj.or.jp/"], "frequency": "monthly",
                        "unit": "tn_jpy", "unit_suffix": "조엔", "data_status": "live",
                        "liabilities_note_ko": "사들인 대금을 누가 들고 있는가.",
                        "assets_note_ko": "일본은행이 무엇을 사들였는가.",
                        "stack_note_ko": ("자산의 대부분이 국채이고, 그 대금이 은행 당좌예금(지준)으로 쌓여 있는 구조입니다. "
                                          "국채 매입 축소(QT)는 국채 밴드와 당좌예금 밴드가 함께 줄어드는 것으로 보입니다."),
                    })


# --------------------------------------------------------------------------
# ECB / Eurosystem
# --------------------------------------------------------------------------

def euro() -> dict[str, Any]:
    def s(key: str) -> Points:
        return [(d, v * 1e-6) for d, v in wps.read_ecb("ILM", key, start="2015-01")]      # €mn -> €tn
    k = lambda item, area: f"W.U2.C.{item}.{area}"  # noqa: E731
    assets = [
        L("mp_sec", "통화정책 보유증권(APP·PEPP)", C["bonds"], "양적완화로 사들인 채권. 만기분을 재투자하지 않아 줄고 있습니다."),
        L("other_sec", "기타 유로 증권", C["bonds2"], "통화정책 목적이 아닌 유로 표시 증권."),
        L("lending", "은행 대출(MRO·LTRO·TLTRO)", C["lending"], "통화정책 대출. 2022년 TLTRO 상환으로 크게 줄었습니다."),
        L("fx", "외화 자산", C["fx"], "유로 밖 거주자에 대한 외화 표시 청구권."),
        L("gold", "금", C["gold"], "금과 금 청구권(시가 평가)."),
    ]
    liabilities = [
        L("deposit_facility", "예금기구(DFR)", C["reserves"], "은행이 예금금리를 받고 맡긴 초과 유동성. 연준의 지준에 해당합니다."),
        L("current", "당좌계정(지준)", "#fb923c", "은행 당좌계정(필요지준 포함)."),
        L("currency", "은행권", C["currency"], "유통 중인 유로 은행권."),
        L("gov", "정부예금", C["gov"], "유로존 중앙정부가 유로시스템에 둔 예금."),
    ]
    keys = {"mp_sec": k("A070100", "U2.EUR"), "other_sec": k("A070200", "U2.EUR"), "lending": k("A050000", "U2.EUR"),
            "fx": k("A020000", "U4.Z06"), "gold": k("A010000", "Z5.Z0Z"), "deposit_facility": k("L020200", "U2.EUR"),
            "current": k("L020100", "U2.EUR"), "currency": k("L010000", "Z5.EUR"), "gov": k("L050100", "U2.EUR")}
    series = {name: s(key) for name, key in keys.items()}
    return cb.block(total=s(k("T000000", "Z5.Z01")), assets=assets, liabilities=liabilities, series=series,
                    asset_residual=OTHER_A, liability_residual=OTHER_L, since="2016-01-01", step=2, meta={
                        "source": "ECB Data Portal ILM (유로시스템 주간 재무제표), 금요일 기준",
                        "source_urls": ["https://data.ecb.europa.eu/data/datasets/ILM"], "frequency": "weekly",
                        "unit": "tn_eur", "unit_suffix": "조 유로", "data_status": "live",
                        "sampling_note_ko": "표시는 2주 간격으로 솎아낸 시계열입니다(원자료는 주간).",
                        "liabilities_note_ko": "풀린 유로가 어디에 머물러 있는가.",
                        "assets_note_ko": "유로시스템이 무엇을 사고 빌려주었는가.",
                        "stack_note_ko": ("부채 쪽 '예금기구'가 연준의 지급준비금에 해당하는 초과 유동성입니다. 자산 쪽 "
                                          "보유증권과 은행 대출이 줄어드는 만큼 이 밴드가 얇아집니다. '기타 부채·자본'에는 "
                                          "금·외환 재평가 계정이 들어 있어 금값이 오르면 커집니다."),
                    })


# --------------------------------------------------------------------------
# Bank of England
# --------------------------------------------------------------------------

def england() -> dict[str, Any]:
    def s(code: str) -> Points:
        return [(d, v * 1e-6) for d, v in wps.read_boe(code, "01/Jan/2015")]               # £mn -> £tn
    liabilities = [
        L("reserves", "지급준비금", C["reserves"], "은행이 영란은행에 둔 지준 잔액."),
        L("currency", "은행권", C["currency"], "유통 중인 파운드 은행권."),
        L("fx_bills", "외화 증권 발행", C["fx"], "영란은행이 외환보유액 조달을 위해 발행한 외화 채권·어음."),
    ]
    assets = [
        L("str", "단기 레포(STR)", C["repo"], "1주 레포. 2024년부터 지준 공급의 주 경로가 되며 커지고 있습니다."),
        L("iltr", "지수형 장기 레포(ILTR)", C["lending"], "6개월 만기 장기 레포."),
        L("tfsme", "TFSME", "#34d399", "코로나 때 중소기업 대출 연계로 공급한 4년 자금. 만기 상환으로 줄고 있습니다."),
    ]
    apf = {"id": "apf_other", "label_ko": "APF 대출 등(잔차)", "color": C["bonds"],
           "note_ko": ("부채 합계에서 위 레포·TFSME를 뺀 나머지. 대부분은 양적완화 길트를 보유한 자산매입기구(APF)에 대한 "
                       "대출입니다. 영란은행이 이 항목을 주간으로 따로 공표하지 않아 잔차로 계산했습니다.")}
    codes = {"reserves": "RPWB56A", "currency": "RPWB55A", "fx_bills": "RPWB59A",
             "str": "RPWB67A", "iltr": "RPWB69A", "tfsme": "RPWZOQ4"}
    series = {k: s(c) for k, c in codes.items()}
    # No weekly total since 2014: the total is the three weekly liability lines.
    by = [dict(series[k]) for k in ("reserves", "currency", "fx_bills")]
    total = [(d, sum(m[d] for m in by)) for d, _ in series["reserves"] if all(d in m for m in by)]
    return cb.block(total=total, assets=assets, liabilities=liabilities, series=series,
                    asset_residual=apf, liability_residual=None, since="2016-01-01", step=2, meta={
                        "source": "Bank of England Database(IADB) 주간 잔액 RPWB55A·56A·59A·67A·69A, RPWZOQ4",
                        "source_urls": ["https://www.bankofengland.co.uk/boeapps/database/"], "frequency": "weekly",
                        "unit": "tn_gbp", "unit_suffix": "조 파운드", "data_status": "live",
                        "total_label_ko": "주간 공표 부채 합계",
                        "sampling_note_ko": "표시는 2주 간격으로 솎아낸 시계열입니다(원자료는 수요일 주간).",
                        "liabilities_note_ko": "영란은행이 주간으로 공표하는 세 부채 항목.",
                        "assets_note_ko": "그 부채를 만든 자산 -- 레포와 APF.",
                        "stack_note_ko": ("영란은행은 2014년 이후 주간 총자산을 공표하지 않습니다(분기 총액은 약 5분기 늦게 "
                                          "나옵니다). 그래서 이 그래프의 총액은 주간 공표 부채 3개 항목(지준·은행권·외화증권)의 "
                                          "합이며, 자본·기타 부채는 빠져 있습니다. 자산 쪽 'APF 대출 등'은 그 합에서 레포·TFSME를 "
                                          "뺀 잔차입니다."),
                    })


# --------------------------------------------------------------------------
# People's Bank of China
# --------------------------------------------------------------------------

PBC = "https://www.pbc.gov.cn"
PBC_INDEX = PBC + "/diaochatongjisi/116219/116319/index.html"
PBC_ROWS = {  # Chinese row label (as printed) -> layer id; first match wins
    "总资产": "total", "外汇": "fx", "对政府债权": "claims_gov", "对其他存款性公司债权": "claims_banks",
    "货币发行": "currency", "其他存款性公司存款": "reserves", "政府存款": "gov", "发行债券": "bonds_issued",
}


def _pbc_get(path: str) -> bytes:
    return jps._get(path if path.startswith("http") else PBC + path, timeout=60)


def pbc_year_pages(index_html: str) -> dict[int, str]:
    out = {}
    for href, year in re.findall(r"href='(/diaochatongjisi/116219/116319/[^']+/index\.html)'[^>]*guidlevel01[^>]*>(\d{4})年", index_html):
        out.setdefault(int(year), href)
    return out


def _link_after(text: str, label: str, pattern: str) -> str | None:
    i = text.find(label)
    if i < 0:
        return None
    m = re.search(pattern, text[i:i + 4000])
    return m.group(1) if m else None


def parse_pbc_table(raw: bytes) -> dict[str, Points]:
    """The 货币当局资产负债表 HTML (GBK or UTF-8): header row of YYYY.MM, one row per account, 亿元."""
    try:                                     # most years are GBK; 2017-2018 were re-saved as UTF-8
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="replace")
    rows = []
    for r in re.findall(r"<tr.*?</tr>", text, re.S | re.I):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip()
                 for c in re.findall(r"<td.*?</td>", r, re.S | re.I)]
        rows.append(cells)
    head = next((r for r in rows if r and re.fullmatch(r"\d{4}\.\d{1,2}", (r[1] if len(r) > 1 else "") or "")), None)
    if not head:
        raise ValueError("PBoC table: no month header")
    months = [f"{c[:4]}-{int(c[5:]):02d}" if re.fullmatch(r"\d{4}\.\d{1,2}", c) else None for c in head[1:]]
    out: dict[str, Points] = {}
    for r in rows:
        if not r or not r[0]:
            continue
        name = r[0].split(" ")[0].replace("　", "").strip()
        key = PBC_ROWS.get(name)
        if not key or key in out:
            continue
        pts = []
        for m, c in zip(months, r[1:]):
            try:
                if m and c:
                    pts.append((ups.month_end(m + "-01"), float(c.replace(",", "")) * 1e-4))    # 亿元 -> 조 위안
            except ValueError:
                continue
        out[key] = pts
    if "total" not in out:
        raise ValueError("PBoC table: no 总资产 row")
    return out


def china(first_year: int = 2015) -> dict[str, Any]:
    years = pbc_year_pages(_pbc_get(PBC_INDEX).decode("utf-8", errors="replace"))
    merged: dict[str, dict[str, float]] = {}
    for year in sorted(y for y in years if y >= first_year):
        page = _pbc_get(years[year]).decode("utf-8", errors="replace")
        m = re.search(r"href='([^']+/index\.html)'[^>]*>\s*货币统计概览", page)
        survey = m.group(1) if m else years[year]
        sub = _pbc_get(survey).decode("utf-8", errors="replace")
        htm = _link_after(sub, "货币当局资产负债表", r'href="(/diaochatongjisi/[^"]+\.htm)"')
        if not htm:
            raise ValueError(f"PBoC {year}: no 货币当局资产负债表 link")
        for key, pts in parse_pbc_table(_pbc_get(htm)).items():
            merged.setdefault(key, {}).update(dict(pts))
    series = {k: sorted(v.items()) for k, v in merged.items()}
    assets = [
        L("fx", "외화자산(외환)", C["fx"], "외환보유액에 대응하는 외화 자산. 2014년까지 인민은행 자산 증가의 엔진이었습니다."),
        L("claims_banks", "은행 대출(MLF·PSL·재대출)", C["lending"], "시중은행에 대한 청구권. 2015년 이후 유동성 공급의 주 경로입니다."),
        L("claims_gov", "정부 채권(국채)", C["bonds"], "중앙정부에 대한 청구권(특별국채 등)."),
    ]
    liabilities = [
        L("reserves", "지급준비금(은행 예금)", C["reserves"], "시중은행이 인민은행에 맡긴 예금 -- 지급준비율 인하 때 줄어듭니다."),
        L("currency", "화폐발행", C["currency"], "발행 화폐."),
        L("gov", "정부예금", C["gov"], "재정 예금. 세수가 몰리는 달에 늘어납니다."),
    ]
    return cb.block(total=series["total"], assets=assets, liabilities=liabilities, series=series,
                    asset_residual=OTHER_A, liability_residual=OTHER_L, since="2015-01-01", meta={
                        "source": "중국인민은행 조사통계사 货币当局资产负债表(통화당국 대차대조표), 월말",
                        "source_urls": [PBC_INDEX], "frequency": "monthly", "unit": "tn_cny",
                        "unit_suffix": "조 위안", "data_status": "live",
                        "liabilities_note_ko": "본원통화가 어디에 머물러 있는가.",
                        "assets_note_ko": "인민은행이 무엇으로 돈을 풀었는가.",
                        "stack_note_ko": ("자산 쪽에서 외화자산이 정체한 뒤 은행 대출(MLF·PSL 등)이 그 자리를 채운 것이 "
                                          "2015년 이후 중국 통화 공급의 구조 변화입니다. 부채 쪽 지급준비금은 지준율 인하 때마다 "
                                          "계단식으로 줄어듭니다."),
                    })


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------

BANKS: dict[str, tuple[str, Callable[[], dict[str, Any]]]] = {
    "KOR": ("bok_total_assets", korea),
    "JPN": ("boj_total_assets", japan),
    "EMU": ("ecb_total_assets", euro),
    "GBR": ("boe_total_assets", england),
    "CHN": ("pboc_total_assets", china),
}

# Cards whose headline this script owns (the others already have a live engine for the total).
OWN_HEADLINE = {
    "GBR": {"label_ko": "BOE 대차대조표", "unit": "bn_gbp", "format": "bn0", "fmt": lambda v: f"£{v * 1000:,.0f}B",
            "note_ko": ("영란은행이 주간으로 공표하는 부채 3개 항목(지급준비금·은행권·외화증권)의 합입니다. 2014년 이후 "
                        "주간 총자산은 공표되지 않아(분기 총액은 약 5분기 지연) 이 합을 대차대조표 규모로 씁니다 -- 자본·기타 "
                        "부채는 빠져 있습니다. 카드를 열면 부채·자산 구성이 나옵니다. IADB RPWB55A·56A·59A."),
            "cadence": "weekly", "scale": 1000.0},
    "CHN": {"label_ko": "PBOC 총자산", "unit": "tn_cny", "format": "tn1", "fmt": lambda v: f"¥{v:,.1f}T",
            "note_ko": ("중국인민은행 통화당국 대차대조표의 총자산(월말, 조 위안)입니다. 카드를 열면 부채·자산 구성이 나옵니다. "
                        "인민은행 조사통계사 货币当局资产负债表."),
            "cadence": "monthly", "scale": 1.0},
}


def headline(iso: str, card: dict[str, Any], bs: dict[str, Any], full_total: Points, now: str) -> None:
    spec = OWN_HEADLINE[iso]
    d, v = full_total[-1]
    year_ago = [x for x in full_total if x[0] <= f"{int(d[:4]) - 1}{d[4:]}"]
    card.update({
        "category": "liquidity", "label_ko": spec["label_ko"], "unit": spec["unit"], "format": spec["format"],
        "value": round(v * spec["scale"], 4), "display": spec["fmt"](v), "display_chip": spec["fmt"](v),
        "change_1y_pct": round((v / year_ago[-1][1] - 1) * 100, 2) if year_ago else None, "change_1m_pct": None,
        "asof": d, "observed_at": d, "reference_period": d[:7] if spec["cadence"] == "monthly" else d,
        "history": ups.history_block([(x, round(y * spec["scale"], 4)) for x, y in full_total], spec["cadence"]),
        "source": bs["source"], "source_urls": bs["source_urls"], "quality": "live", "data_status": "live",
        "refresh_tier": spec["cadence"], "chart_type": "line", "note_ko": spec["note_ko"], "retrieved_at": now,
    })
    card.pop("hidden", None)


def ensure_card(country: dict[str, Any], card_id: str) -> dict[str, Any]:
    by_id = {i["id"]: i for i in country["indicators"]}
    if card_id in by_id:
        return by_id[card_id]
    card = {"id": card_id, "category": "liquidity"}
    country["indicators"].append(card)
    return card


def ensure_chip(country: dict[str, Any], card: dict[str, Any]) -> None:
    liq = country.setdefault("categories", {}).setdefault("liquidity", [])
    chip = next((c for c in liq if c.get("id") == card["id"]), None)
    if chip is None:
        chip = {"id": card["id"]}
        liq.insert(0, chip)
    for k in ("label_ko", "display", "value", "unit", "change_1m_pct", "change_1y_pct", "asof", "note_ko",
              "observed_at", "source", "data_status", "chart_type"):
        chip[k] = card.get(k)
    chip.pop("hidden", None)


def main(argv: list[str]) -> int:
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else set(BANKS)
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    by_iso = {c["iso3"]: c for c in pack["countries"]}
    now, failures = ups.now_iso(), []
    for iso, (card_id, build) in BANKS.items():
        if iso not in only:
            continue
        try:
            bs = build()
            bad = cb.latest_check(bs)
            if bad:
                raise ValueError("; ".join(bad))
        except Exception as exc:  # noqa: BLE001 -- one bank must not block the others
            failures.append(f"{iso}: {str(exc)[:200]}")
            continue
        country = by_iso[iso]
        card = ensure_card(country, card_id)
        if iso in OWN_HEADLINE:
            full = [(d, v) for d, v in zip(bs["dates"], bs["total"]["values"]) if v is not None]
            headline(iso, card, bs, full, now)
            ensure_chip(country, card)
        card["balance_sheet"] = bs
        print(f"{iso} {card_id}: {len(bs['dates'])} points to {bs['asof']}, total {bs['total']['values'][-1]:.3f} {bs['unit_suffix']}")
        for s in bs["sides"]:
            print(f"  [{s['label_ko']}] " + ", ".join(f"{l['label_ko']} {l['values'][-1]}" for l in s["layers"]))
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
