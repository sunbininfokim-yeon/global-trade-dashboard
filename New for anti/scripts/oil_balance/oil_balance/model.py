"""World oil balance -> OECD inventories -> a Brent 'fair value', and how far Brent strays from it.

Same skeleton as the bank research it is meant to check (JP Morgan, 2026-11: 'when geopolitics is hard to
call, go back to first principles'): supply minus demand sets the stock change, stocks set the price.

  days of cover   OECD commercial stocks / OECD demand (EIA STEO, monthly)
  deviation       days of cover minus the average of the same month in the five years before
  fair value      log(Brent) = a + b * deviation, fitted on FIT_FROM..FIT_TO (after the shale build-out;
                  over 2005-2014 the same fit leaves 2011-14 $110 oil with normal stocks unexplained)
  forward         EIA's own stock path (its forecast months) through the same line

What it does not do: it has no view of its own on supply or demand -- the forward path is EIA's balance,
and the scenario lever only moves OECD stocks.
"""

from __future__ import annotations

import math
import statistics as st
from typing import Any

FIT_FROM, FIT_TO = "2015-01", "2025-12"


def days_of_cover(stocks: dict[str, float], demand: dict[str, float]) -> dict[str, float]:
    return {m: stocks[m] / demand[m] for m in stocks if demand.get(m)}


def deviation(doc: dict[str, float]) -> dict[str, float]:
    out = {}
    for m, v in doc.items():
        prev = [doc.get(f"{int(m[:4]) - k}{m[4:]}") for k in range(1, 6)]
        if all(p is not None for p in prev):
            out[m] = v - sum(prev) / 5
    return out


def fit(dev: dict[str, float], brent: dict[str, float], lo: str = FIT_FROM, hi: str = FIT_TO) -> dict[str, float]:
    ms = [m for m in sorted(dev) if lo <= m <= hi and m in brent]
    xs, ys = [dev[m] for m in ms], [math.log(brent[m]) for m in ms]
    mx, my = st.mean(xs), st.mean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    r2 = 1 - sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / sum((y - my) ** 2 for y in ys)
    return {"a": a, "b": b, "r2": r2, "n": len(ms), "from": ms[0], "to": ms[-1]}


def fair_value(dev: dict[str, float], coef: dict[str, float]) -> dict[str, float]:
    return {m: math.exp(coef["a"] + coef["b"] * d) for m, d in dev.items()}


def runs(flags: list[bool]) -> list[int]:
    out, n = [], 0
    for f in flags + [False]:
        if f:
            n += 1
        elif n:
            out.append(n)
            n = 0
    return out


def gap_stats(brent: dict[str, float], fv: dict[str, float], lo: str, hi: str, band: float = 15.0) -> dict[str, Any]:
    """Brent minus fair value over the fit window: the largest premium and discount, and how long
    stretches with a premium above `band` dollars lasted."""
    ms = [m for m in sorted(fv) if lo <= m <= hi and m in brent]
    gap = {m: brent[m] - fv[m] for m in ms}
    top = max(gap, key=gap.get)
    low = min(gap, key=gap.get)
    above = runs([gap[m] > band for m in ms])
    return {"max_premium": round(gap[top], 1), "max_premium_month": top, "max_discount": round(gap[low], 1),
            "max_discount_month": low, "band": band, "episodes_above_band": len(above),
            "avg_months_above_band": round(st.mean(above), 1) if above else None,
            "months_above_band": sum(above), "months": len(ms)}
