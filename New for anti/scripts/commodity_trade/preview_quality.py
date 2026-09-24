"""Conservative publication hints, not proof of incomplete source reporting."""
from math import isfinite
from statistics import median

POLICY = "comtrade-preview-publication-v1"


def _number(value):
    return type(value) in (int, float) and isfinite(value) and value >= 0


def annotate_preview_series(series):
    """Keep raw observations; flag drops against earlier, comparable observations.

    Prefer USD (available even when net weight disappears); otherwise compare
    native values only within the exact same unit. Exclude held points from
    the baseline. A single prior month is weak evidence, recorded explicitly.
    Zero is preserved, not reinterpreted as missing. Non-Preview is untouched.
    """
    points = series.get("points") or []
    accepted = []
    held = []
    for point in sorted(points, key=lambda p: p["month"]):
        if point.get("source") != "comtrade_preview":
            continue
        flags = []
        evidence = None
        if not _number(point.get("value")) or not point.get("unit"):
            flags.append("invalid_observation")
        metric, unit = "primary_value_usd", "usd"
        value = point.get(metric)
        if not _number(value):
            metric, unit, value = "value", point.get("unit"), point.get("value")
        previous = [p for p in accepted if p["month"] < point["month"]
                    and _number(p.get(metric)) and p[metric] > 0
                    and (metric != "value" or p.get("unit") == unit)][-12:]
        if previous and _number(value):
            baseline = median(p[metric] for p in previous)
            ratio = value / baseline
            if ratio < 0.01:
                flags.append("suspected_partial_month")
                evidence = {"metric": metric, "unit": unit, "baseline_median": baseline,
                            "baseline_months": [p["month"] for p in previous],
                            "baseline_count": len(previous), "ratio": ratio, "threshold": 0.01}
        point["publication"] = {
            "policy": POLICY, "status": "hold" if flags else "eligible",
            "eligible_for_display": not flags, "flags": flags, "evidence": evidence,
        }
        (held if flags else accepted).append(point)
    series["publication_summary"] = {
        "policy": POLICY,
        "latest_eligible_month": max((p["month"] for p in accepted), default=None),
        "held_months": sorted({p["month"] for p in held}),
        "eligible_units": sorted({p["unit"] for p in accepted}),
        "note_ko": "급감은 부분 집계 의심이지 확정이 아님. 원본 보존. eligible도 완전성 보증 아님. 서로 다른 단위는 차트·순위에서 분리.",
    }
    quality = series.setdefault("series_quality", {})
    flags = set(quality.get("flags", [])) - {"suspected_partial_month", "invalid_observation"}
    flags.update(flag for p in held for flag in p["publication"]["flags"])
    quality["flags"] = sorted(flags)
