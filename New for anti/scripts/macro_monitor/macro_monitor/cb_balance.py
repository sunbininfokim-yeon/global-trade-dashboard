"""Central bank balance sheets as two stacks, the shape the Fed card already draws (balance_sheet).

Each bank is a list of named layers per side, read from the bank's own statistics, plus a residual band
per side so the stack always reaches the published total: whatever the named layers do not account for
is shown as its own band, never folded into a neighbour (a neighbour that silently absorbs the
remainder looks bigger than it is). A date missing any named layer gets no residual -- a remainder
computed against an incomplete set would absorb whichever layer was missing.

The total is the bank's published total where it publishes one. The Bank of England does not publish a
weekly total any more (the weekly Bank Return stopped in 2014; the quarterly total runs about five
quarters behind), so its total is the sum of the weekly liability lines it does publish, and the card
says so.

All values are trillions of the bank's own currency.
"""

from __future__ import annotations

from typing import Any

Points = list[tuple[str, float]]


def as_of(points: Points, day: str) -> float | None:
    """Latest observation on or before `day` (points sorted ascending)."""
    hit = None
    for d, v in points:
        if d <= day:
            hit = v
        else:
            break
    return hit


def exact(points: Points) -> dict[str, float]:
    return dict(points)


def side(layers: list[dict[str, Any]], series: dict[str, Points], dates: list[str], totals: list[float | None],
         residual: dict[str, Any] | None) -> list[dict[str, Any]]:
    """One side's layers on `dates`. A layer reads its own series on the same date (no carrying forward:
    every layer of a balance sheet is published for the same date). `residual` (or None) closes the side
    to the total."""
    cols: dict[str, list[float | None]] = {}
    for spec in layers:
        got = exact(series[spec["id"]])
        cols[spec["id"]] = [None if got.get(d) is None else round(got[d], 4) for d in dates]
    out = [{k: spec[k] for k in ("id", "label_ko", "color", "note_ko") if k in spec} | {"values": cols[spec["id"]]}
           for spec in layers]
    if residual:
        rest: list[float | None] = []
        for i, tot in enumerate(totals):
            named = [cols[s["id"]][i] for s in layers]
            rest.append(None if tot is None or any(v is None for v in named) else round(tot - sum(named), 4))
        out.append({k: residual[k] for k in ("id", "label_ko", "color", "note_ko") if k in residual} | {"values": rest})
    return out


def thin(dates: list[str], step: int) -> list[int]:
    """Every `step`-th index, always ending on the last one (the headline quotes the last date)."""
    keep = list(range(0, len(dates), step))
    if dates and keep[-1] != len(dates) - 1:
        keep.append(len(dates) - 1)
    return keep


def block(*, total: Points, assets: list[dict[str, Any]], liabilities: list[dict[str, Any]],
          series: dict[str, Points], asset_residual: dict[str, Any] | None, liability_residual: dict[str, Any] | None,
          since: str, step: int = 1, meta: dict[str, Any]) -> dict[str, Any]:
    """The balance_sheet block macro.js draws: dates, total, and the assets/liabilities sides."""
    pts = [(d, v) for d, v in total if d >= since]
    if not pts:
        raise ValueError("no total observations in the window")
    dates = [d for d, _ in pts]
    totals: list[float | None] = [round(v, 4) for _, v in pts]
    a = side(assets, series, dates, totals, asset_residual)
    li = side(liabilities, series, dates, totals, liability_residual)
    keep = thin(dates, step)
    pick = lambda xs: [xs[i] for i in keep]  # noqa: E731
    for lay in a + li:
        lay["values"] = pick(lay["values"])
    out = dict(meta)
    out.update({
        "asof": dates[-1],
        "dates": pick(dates),
        "total": {"label_ko": meta.get("total_label_ko", "총자산"), "values": pick(totals)},
        "sides": [
            {"id": "liabilities", "label_ko": "부채", "note_ko": meta.get("liabilities_note_ko", ""), "layers": li},
            {"id": "assets", "label_ko": "자산", "note_ko": meta.get("assets_note_ko", ""), "layers": a},
        ],
    })
    out.pop("total_label_ko", None)
    out.pop("liabilities_note_ko", None)
    out.pop("assets_note_ko", None)
    return out


def latest_check(bs: dict[str, Any], tol: float = 1e-3) -> list[str]:
    """Sides that do not add up to the total on the last date (should be none when residuals close them)."""
    bad = []
    tot = bs["total"]["values"][-1]
    for s in bs["sides"]:
        vals = [l["values"][-1] for l in s["layers"]]
        if any(v is None for v in vals):
            bad.append(f"{s['id']}: missing layer on {bs['asof']}")
        elif abs(sum(vals) - tot) > tol * max(abs(tot), 1):
            bad.append(f"{s['id']}: {sum(vals):.4f} vs total {tot:.4f}")
    return bad
