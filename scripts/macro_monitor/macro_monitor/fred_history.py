"""FRED history transforms: YoY / MoM pure functions."""
from __future__ import annotations

def yoy_pct_from_index(values):
    if len(values) < 13:
        return None
    a, b = values[-1], values[-13]
    if b == 0:
        return None
    return (a / b - 1.0) * 100.0

def mom_delta(values):
    if len(values) < 2:
        return None
    return values[-1] - values[-2]
