"""Calendar-safe transforms shared by CPI research and standard-library jobs."""
import math
import re


def shift(month: str, offset: int) -> str:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        raise ValueError(f"invalid reference month: {month}")
    serial = int(month[:4]) * 12 + int(month[5:]) - 1 + offset
    return f"{serial // 12:04d}-{serial % 12 + 1:02d}"


def monthly_changes(points):
    levels = {}
    for month, value in points:
        shift(month, 0)
        if value is not None and math.isfinite(value) and value > 0:
            levels[month] = value
    return {
        month: (levels[month] / levels[prev] - 1) * 100
        for month in sorted(levels)
        if (prev := shift(month, -1)) in levels
    }
