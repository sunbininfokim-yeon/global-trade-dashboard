"""One delinquency card per country instead of five or six: delinquency and charge-offs by borrower, drawn as
coloured lines with a dot on every observation.

USA  host `delinq_all` (config/free_cards_v1.json). Panels from the Fed Board's 'Charge-Off and Delinquency Rates
     on Loans and Leases at Commercial Banks' (FRED, keyless, quarterly, seasonally adjusted): delinquency and net
     charge-off rates for all loans, residential mortgages, commercial real estate, credit cards, other consumer
     loans and business (C&I) loans, plus all-loans delinquency against charge-offs.
KOR  host `delinq_monthly` (kr_delinq_monthly.py). Panels re-drawn from the cards the Korean bank/non-bank
     pipelines already build (FSS FISIS): monthly by segment, quarterly household vs business, new delinquency,
     bank vs savings bank / card / capital, and new delinquency against charge-offs and other resolutions.

The absorbed cards stay in the pack (their pipelines keep them current and this module reads them); they are
hidden through config/hidden_cards_v1.json. Idempotent: every run rebuilds the host's panels from scratch.
"""

from __future__ import annotations

from typing import Callable

from . import us_public_series as ups

US_HOST, KR_HOST = "delinq_all", "delinq_monthly"
US_LABEL, KR_LABEL = "대출 연체율·상각률", "대출 연체율·상각"
US_ABSORBED = ("delinq_card", "delinq_mortgage", "delinq_business", "chargeoff_all")
KR_ABSORBED = ("delinq_all", "early_delinq", "sb_delinq", "card_delinq", "capital_delinq")

# (label, delinquency series, charge-off series)
US_SEGMENTS = [
    ("전체", "DRALACBS", "CORALACBS"),
    ("주택담보", "DRSFRMACBS", "CORSFRMACBS"),
    ("상업용 부동산", "DRCRELEXFACBS", "CORCREXFACBS"),
    ("신용카드", "DRCCLACBS", "CORCCACBS"),
    ("기타 소비자", "DROCLACBS", "COROCLACBS"),
    ("기업(C&I)", "DRBLACBS", "CORBLACBS"),
]


def _qlabel(d: str) -> str:
    return f"{d[2:4]}.{(int(d[5:7]) - 1) // 3 + 1}Q"


def us_panels(fred: Callable[[str], ups.Points], quarters: int = 40) -> list[dict]:
    data = {sid: dict(fred(sid)) for _, a, b in US_SEGMENTS for sid in (a, b)}
    axis = sorted(set().union(*(set(v) for v in data.values())))[-quarters:]
    dates = [_qlabel(d) for d in axis]

    def col(sid: str) -> list:
        return [round(data[sid][d], 2) if d in data[sid] else None for d in axis]

    common = {"type": "lines", "markers": True, "unit": "%", "dates": dates, "compare_ko": "직전 분기"}
    return [
        {**common, "id": "us_delinq_rates", "label": "연체율",
         "series": [{"label": lab, "values": col(a)} for lab, a, _ in US_SEGMENTS],
         "note_ko": "상업은행 대출 중 30일 이상 연체된 비율(계절조정, %). 연준 이사회 분기 통계."},
        {**common, "id": "us_chargeoff_rates", "label": "상각률",
         "series": [{"label": lab, "values": col(b)} for lab, _, b in US_SEGMENTS],
         "note_ko": "순대손상각률: 회수 불능으로 털어 낸 대출(회수분 차감) / 평균 대출, 연율(계절조정, %). 연체가 상각으로 넘어가는 데는 보통 몇 분기가 걸립니다."},
        {**common, "id": "us_delinq_vs_chargeoff", "label": "연체 vs 상각 (전체)",
         "series": [{"label": "연체율", "values": col("DRALACBS")}, {"label": "상각률", "values": col("CORALACBS")}],
         "note_ko": "전체 대출의 연체율과 상각률. 연체가 먼저 오르고 상각이 뒤따르는지 봅니다."},
    ]


def _panel(ind: dict | None, pid: str) -> dict | None:
    return next((p for p in (ind or {}).get("panels") or [] if p.get("id") == pid), None)


def _as_lines(p: dict | None, new_id: str, label: str, note: str, absolute: bool = False, keep: tuple[str, ...] = ()) -> dict | None:
    if not p or not p.get("dates") or not p.get("series"):
        return None
    series = [s for s in p["series"] if not keep or s.get("label") in keep]
    if absolute:
        series = [{**s, "values": [abs(v) if isinstance(v, (int, float)) else None for v in s["values"]]} for s in series]
    return {"id": new_id, "label": label, "type": "lines", "markers": True, "unit": p.get("unit", ""),
            "dates": p["dates"], "series": series, "compare_ko": p.get("compare_ko") or "직전 분기", "note_ko": note}


def kr_panels(by_id: dict[str, dict]) -> list[dict]:
    host = by_id.get(KR_HOST)
    q = by_id.get("delinq_all")
    m_seg = _panel(host, "m_segments")
    out = [
        {**m_seg, "markers": True, "label": "부문별 연체율(월)", "compare_ko": "직전 달"} if m_seg else None,
        _as_lines(_panel(q, "segments"), "kr_hh_corp_q", "가계·기업(분기)",
                  "국내은행 원화대출 연체율(1개월 이상, 분기말, %). 금감원 FISIS."),
        _as_lines(_panel(by_id.get("early_delinq"), "new_segments"), "kr_new_q", "신규연체율(분기)",
                  "분기 중 새로 연체된 금액 / 분기초 대출(%). 연체율보다 먼저 움직입니다."),
        _as_lines(_panel(by_id.get("sb_delinq"), "sector_compare"), "kr_sectors", "업권별",
                  "은행·저축은행·카드사·캐피탈의 연체율(분기말, %). 2금융권이 먼저 나빠지는지 봅니다."),
        _as_lines(_panel(q, "flow"), "kr_writeoff", "연체 발생·상각(조원)",
                  "국내은행 분기 중 신규연체 발생액과 정리액(조원): 상각, 정상화 등, 대환. 정리가 신규에 못 미치면 연체 잔액이 쌓입니다.",
                  absolute=True),
        _panel(host, "m_flow"),
        _panel(host, "m_new_rate"),
        _panel(q, "banks_delinq"),
    ]
    return [p for p in out if p]


def _set_host(country: dict, host_id: str, label: str, panels: list[dict]) -> bool:
    """The card opens on its first panel (the coloured lines), not on the single headline series."""
    ind = next((i for i in country.get("indicators") or [] if i.get("id") == host_id), None)
    if not ind or not panels:
        return False
    ui = {**(ind.get("ui") or {}), "first_panel": panels[0]["id"]}
    changed = ind.get("panels") != panels or ind.get("label_ko") != label or ind.get("ui") != ui
    ind["panels"] = panels
    ind["label_ko"] = label
    ind["ui"] = ui
    for chips in (country.get("categories") or {}).values():
        for c in chips:
            if c.get("id") == host_id and c.get("label_ko") != label:
                c["label_ko"] = label
                changed = True
    return changed


def apply(pack: dict, us: list[dict] | None) -> list[str]:
    changed = []
    by_iso = {c["iso3"]: c for c in pack["countries"]}
    if us and "USA" in by_iso and _set_host(by_iso["USA"], US_HOST, US_LABEL, us):
        changed.append("USA")
    if "KOR" in by_iso:
        kor = by_iso["KOR"]
        if _set_host(kor, KR_HOST, KR_LABEL, kr_panels({i["id"]: i for i in kor.get("indicators") or []})):
            changed.append("KOR")
    return changed


def hide_keys() -> list[str]:
    return [f"USA:{i}" for i in US_ABSORBED] + [f"KOR:{i}" for i in KR_ABSORBED]
