"""Palm kernel shell (PKS) supply read-out, derived from the palm CPO line.

PKS is the shell left after the kernel is cracked out at the mill, sold as
solid biomass fuel (GS Global buys it for Korean power plants). No country
publishes PKS output, so it is derived:

  PKS / CPO ~ 0.25 (range 0.22-0.30): mills extract ~20-22% of fresh fruit
  bunch weight as CPO and ~5-6.5% as shell. Industry rule of thumb, not a
  measured national ratio, and the screen says so.

The direction follows the palm weather read-out: an "unfavorable" call whose
history supports it moves PKS down by the same mean shortfall seen in past
unfavorable years. Nothing else is added: PKS adds no information beyond the
palm line, only a unit a biomass buyer reads.
"""
from __future__ import annotations

RATIO = 0.25
RATIO_RANGE = (0.22, 0.30)


def outlook(trend_kt: float | None, conditions: dict | None) -> dict | None:
    if trend_kt is None or not conditions:
        return None
    trend = trend_kt * RATIO
    out = {
        "ratio_to_cpo": RATIO,
        "trend_kt": round(trend),
        "trend_range_kt": [round(trend_kt * RATIO_RANGE[0]), round(trend_kt * RATIO_RANGE[1])],
        "direction": "flat",
        "adjusted_kt": None,
    }
    supported = conditions.get("unfavorable_supported", True) is not False
    mean = conditions.get("unfavorable_mean_pct")
    if conditions.get("verdict") == "unfavorable" and supported and mean is not None and mean < 0:
        out["direction"] = "down"
        out["adjusted_kt"] = round(trend * (1 + mean / 100))
        out["summary_ko"] = (f"PKS(팜 껍질) 공급 추정: 추세 약 {trend:,.0f}천 t → 불리 판정이라 감소 쪽, "
                             f"과거 불리 해 평균({mean:+.1f}%) 적용 시 약 {out['adjusted_kt']:,.0f}천 t")
    else:
        out["summary_ko"] = f"PKS(팜 껍질) 공급 추정: 추세 약 {trend:,.0f}천 t, 기상 판정상 뚜렷한 증감 신호 없음"
    out["note_ko"] = "CPO의 약 25%(업계 경험치 22~30%)로 환산한 추정이며 공식 통계가 아니다."
    return out
