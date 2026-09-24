"""When the next print is due, for every macro-monitor indicator.

This does not invent a value and does not pretend a typical window is an
official timestamp. ``next_release_on`` is set only when the rule is a real
calendar fact (the next weekday, the next Thursday for a known weekly
release). Monthly and quarterly series get a window and a note that names
the institution. Cards still on fixture data ignore their month-end ``asof``:
that date was never a release.

``sovereign_cds_5y`` stays manual. There is no free source to schedule.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

BASIS_SESSION = "next_session"
BASIS_WEEKDAY = "weekday"
BASIS_WINDOW = "typical_window"
BASIS_NONE = "not_automated"

# Day-of-month windows in the month after the reference month. These are the
# usual publication bands, not a claim that the agency has posted that date.
CPI_WINDOWS: dict[str, tuple[int, int, str]] = {
    "USA": (10, 14, "미국 노동통계국(BLS). 보통 다음 달 10–14일, 동부시간 08:30."),
    "KOR": (1, 4, "통계청. 보통 다음 달 초. 정확한 날은 보도일정."),
    "JPN": (15, 25, "총무성. 보통 다음 달 중하순."),
    "GBR": (14, 22, "영국 통계청(ONS). 보통 다음 달 중순."),
    "EMU": (15, 20, "유로스타트. 확정치는 보통 다음 달 중순. 속보는 월말에 따로 나옴."),
    "CAN": (15, 21, "캐나다 통계청. 보통 다음 달 중순."),
    "AUS": (20, 31, "호주 통계청(ABS). 분기 CPI는 분기 다음 달 말, 월간 지표는 그 이전."),
    "CHE": (1, 6, "스위스 연방통계청. 보통 다음 달 초."),
    "BRA": (8, 12, "IBGE. IPCA는 보통 다음 달 8–12일."),
    "CHN": (9, 15, "국가통계국. 보통 다음 달 9–15일."),
    "ZAF": (15, 24, "통계청(Stats SA). 보통 다음 달 중순."),
    "IND": (10, 14, "MoSPI. 보통 다음 달 12일 전후."),
}

CPI_IDS = {
    "cpi_yoy", "core_cpi_yoy", "core_cpi_jp", "core_core_cpi", "tokyo_cpi",
    "hicp_yoy", "core_hicp_yoy", "composite_cpi", "ipca", "ipca_15",
    "monthly_cpi", "trimmed_mean_cpi", "cpi_trim", "cpi_median", "services_cpi",
    "ppi_yoy", "wpi_yoy",
}

POLICY_IDS = {
    "sarb_repo", "bank_rate", "call_rate", "rba_cash_rate", "snb_policy_rate",
    "selic_rate", "rbi_repo", "boi_rate", "cbr_key_rate", "hk_base_rate",
    "cbc_discount", "nbk_base_rate", "deposit_facility", "mro_rate", "mlf_rate",
    "sbv_refinancing", "sbv_discount", "bok_base_rate", "effr",
    "boc_overnight",
}

WEEKLY_THURSDAY = {
    "fed_total_assets", "tga", "on_rrp", "fed_mbs", "initial_claims",
    "discount_window", "fima_repo",
}

MARKET_TIERS = {"market_daily", "market_intraday"}


def _month_end(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _window(year: int, month: int, start_day: int, end_day: int) -> tuple[date, date]:
    last = _month_end(year, month)
    return date(year, month, min(start_day, last)), date(year, month, min(end_day, last))


def _upcoming_window(today: date, start_day: int, end_day: int) -> tuple[date, date]:
    year, month = today.year, today.month
    for _ in range(14):
        start, end = _window(year, month, start_day, end_day)
        if end >= today:
            return start, end
        year, month = _shift_month(year, month, 1)
    raise RuntimeError("no upcoming window")


def _window_after_reference(today: date, reference: date, start_day: int, end_day: int) -> tuple[date, date]:
    """Release window in the month after ``reference``, stepped forward once it has passed."""
    year, month = _shift_month(reference.year, reference.month, 1)
    for _ in range(18):
        start, end = _window(year, month, start_day, end_day)
        if end >= today:
            return start, end
        year, month = _shift_month(year, month, 1)
    raise RuntimeError("no window after reference")


def next_business_day(today: date) -> date:
    nxt = today + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def next_weekday(today: date, weekday: int) -> date:
    """The next date with that weekday, including today."""
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def _parse_day(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _real_reference(indicator: dict[str, Any]) -> date | None:
    quality = str(indicator.get("quality") or "")
    source = indicator.get("source")
    if quality == "demo" or source == "fixture_synth":
        return None
    return _parse_day(indicator.get("asof"))


def _pack(
    *,
    basis: str,
    note_ko: str,
    on: date | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    return {
        "next_release_on": on.isoformat() if on else None,
        "next_release_window": (
            {"start": start.isoformat(), "end": end.isoformat()} if start and end else None
        ),
        "next_release_basis": basis,
        "next_release_note_ko": note_ko,
    }


def schedule_for(indicator: dict[str, Any], *, iso3: str, today: date) -> dict[str, Any]:
    iid = str(indicator.get("id") or "")
    tier = indicator.get("refresh_tier")
    reference = _real_reference(indicator)

    if iid == "sovereign_cds_5y":
        return _pack(
            basis=BASIS_NONE,
            note_ko="5년 CDS는 무료 공개 API가 없다. 자동 갱신하지 않는다.",
        )

    if iid == "us_fx_watch":
        start, end = _fx_watch_window(today)
        return _pack(
            basis=BASIS_WINDOW, start=start, end=end,
            note_ko="미국 재무부 환율보고서. 보통 4월과 10–11월이고 날짜는 고정이 아니다. API가 없어 사람이 표를 옮긴다.",
        )

    if iid in POLICY_IDS or tier in {"policy_event", "event"}:
        return _pack(
            basis=BASIS_NONE,
            note_ko="중앙은행·정책 결정일. 회의 사이에 금리가 바뀌지 않을 수 있어, 다음 날을 단정하지 않는다.",
        )

    if iid in CPI_IDS or (iid.endswith("cpi_yoy") and tier == "monthly"):
        start_day, end_day, note = CPI_WINDOWS.get(iso3, (1, 25, "월간 물가. 다음 달 발표가 보통이며 기관 일정표의 정확한 날은 여기 없다."))
        if reference:
            start, end = _window_after_reference(today, reference, start_day, end_day)
        else:
            start, end = _upcoming_window(today, start_day, end_day)
            note = "카드가 아직 합성값이라 관측월을 쓰지 않았다. " + note
        return _pack(basis=BASIS_WINDOW, start=start, end=end, note_ko=note)

    src = str(indicator.get("source") or "")
    if iid in {"bond_10y", "sagb_10y", "bund_10y", "btp_10y"} and "IRLTLT" in src and reference:
        start, end = _window_after_reference(today, reference, 1, 20)
        return _pack(
            basis=BASIS_WINDOW, start=start, end=end,
            note_ko="OECD 장기금리. 월간 공표이고, 다음 달 1–20일이 보통이며 정확한 날은 여기 없다.",
        )

    if iid == "unemployment" and reference and ("UNRATE" in src or "LRHUTTTT" in src):
        start, end = _window_after_reference(today, reference, 1, 25)
        return _pack(
            basis=BASIS_WINDOW, start=start, end=end,
            note_ko="실업률. 월간 공표이고, 다음 달에 나오는 것이 보통이며 정확한 날은 여기 없다.",
        )

    if iid in WEEKLY_THURSDAY:
        nxt = next_weekday(today, 3)  # Thursday
        return _pack(
            basis=BASIS_WEEKDAY, on=nxt,
            note_ko="목요일 발표(연준 H.4.1·신규 실업수당). 휴일 주에는 하루 밀릴 수 있다.",
        )

    if tier in MARKET_TIERS or indicator.get("category") in {"fx", "equity"}:
        nxt = next_business_day(today)
        return _pack(
            basis=BASIS_SESSION, on=nxt,
            note_ko="다음 거래일. 휴장일은 빼지 않았다.",
        )

    if tier == "weekly":
        return _pack(basis=BASIS_WINDOW, note_ko="주 1회. 요일은 기관마다 달라 하루로 단정하지 않는다.")

    if iid == "gdp_yoy" or tier in {"annual", "yearly"}:
        year = reference.year if reference else today.year - 1
        return _pack(
            basis=BASIS_WINDOW,
            note_ko=(
                f"연간 실측. 최신 관측 연도는 {year}년이다. "
                f"{year + 1}년 수치는 그 다음 해에 공개되는 것이 보통이며, 날짜는 고정되어 있지 않다."
            ),
        )

    if tier == "quarterly" or iid in {"gdp_qoq", "gdp", "current_account"}:
        start, end = _next_quarter_release_window(today, reference)
        return _pack(
            basis=BASIS_WINDOW, start=start, end=end,
            note_ko="분기 지표. 분기 종료 후 약 4–8주가 보통이며, 나라마다 통계청 일정이 다르다. IMF 연간 시리즈로는 이 주기를 채울 수 없다.",
        )

    if tier == "semiannual":
        start, end = _fx_watch_window(today)
        return _pack(
            basis=BASIS_WINDOW, start=start, end=end,
            note_ko="반기. 정확한 발표일은 기관 일정에 따른다.",
        )

    if tier == "monthly":
        start, end = _upcoming_window(today, 1, 25)
        return _pack(
            basis=BASIS_WINDOW, start=start, end=end,
            note_ko="월간. 다음 달 안에 나오는 것이 보통이며, 이 지표의 정확한 발표일은 여기 없다.",
        )

    return _pack(
        basis=BASIS_NONE,
        note_ko="발표 주기를 단정할 공식 일정이 없다.",
    )


def _fx_watch_window(today: date) -> tuple[date, date]:
    """Treasury FX report tends to land in April or October–November. Not a fixed day."""
    april = _window(today.year, 4, 1, 30)
    autumn = (date(today.year, 10, 15), date(today.year, 11, 30))
    for start, end in (april, autumn):
        if end >= today:
            return start, end
    return _window(today.year + 1, 4, 1, 30)


def _next_quarter_release_window(today: date, reference: date | None) -> tuple[date, date]:
    anchor = reference or today
    # Next quarter end after the reference month.
    q_end_month = ((anchor.month - 1) // 3 + 1) * 3
    year = anchor.year
    if date(year, q_end_month, _month_end(year, q_end_month)) <= anchor:
        q_end_month += 3
        if q_end_month > 12:
            q_end_month -= 12
            year += 1
    quarter_end = date(year, q_end_month, _month_end(year, q_end_month))
    start = quarter_end + timedelta(days=28)
    end = quarter_end + timedelta(days=56)
    if end < today:
        return _next_quarter_release_window(today, end)
    return start, end


def apply_release_calendar(universe: dict[str, Any], *, today: date) -> int:
    """Stamp next-release fields. Does not change values. Returns the count stamped."""
    stamped = 0
    for country in universe.get("countries") or []:
        iso3 = str(country.get("iso3") or "")
        chips = {
            chip.get("id"): chip
            for chips in (country.get("categories") or {}).values()
            for chip in chips
            if isinstance(chip, dict)
        }
        for indicator in country.get("indicators") or []:
            fields = schedule_for(indicator, iso3=iso3, today=today)
            indicator.update(fields)
            chip = chips.get(indicator.get("id"))
            if chip is not None:
                chip.update(fields)
            stamped += 1
    universe["release_calendar"] = {
        "asof": today.isoformat(),
        "note_ko": "next_release_on 은 요일·거래일처럼 계산이 되는 것만. 월간·분기는 구간(typical_window)이며 공식 타임스탬프가 아니다.",
    }
    return stamped
