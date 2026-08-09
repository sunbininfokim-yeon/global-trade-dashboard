"""Assumption-driven valuation (shipping-scenario style). Pure functions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_valuation_spec(path: Path | None = None) -> dict[str, Any]:
    p = path or (CONFIG_DIR / "valuation.spec.json")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def seed_from_statements(
    amounts: dict[str, float | None],
    *,
    operating_margin_pct: float | None = None,
    fcf: float | None = None,
) -> dict[str, Any]:
    """Calibrate reinvestment / tax / multiples from reported accounts.

    Default scenario JSON is industrial/shipping-ish (Capex 8%, EV/EBITDA 6–10x).
    That systematically undervalues asset-light, high-margin names vs market.
    We seed Capex/DA/tax/NWC from the filing when possible; multiples scale with
    quality (margin + low Capex). Still assumption-driven — not a market price match.
    """
    rev = amounts.get("REVENUE")
    out: dict[str, Any] = {
        "capex_to_sales": None,
        "da_to_sales": None,
        "sales_to_nwc": None,
        "tax_rate": None,
        "ev_ebitda_multiples": {"bear": 6.0, "base": 8.0, "bull": 10.0},
        "quality_tier": "industrial",
        "notes_ko": [],
    }
    if rev and rev > 0:
        capex = amounts.get("CAPEX")
        da = amounts.get("DEPRECIATION")
        ca = amounts.get("CURRENT_ASSETS")
        cl = amounts.get("CURRENT_LIABILITIES")
        tax_e = amounts.get("INCOME_TAX_EXPENSE")
        pbt = amounts.get("PROFIT_BEFORE_TAX")

        if capex is not None:
            # Capex often reported as cash outflow (positive) in our map
            out["capex_to_sales"] = round(abs(float(capex)) / float(rev), 4)
        if da is not None:
            out["da_to_sales"] = round(abs(float(da)) / float(rev), 4)
        if ca is not None and cl is not None:
            # Apple-like platforms can have negative NWC; floor at 0 for FCFF drag
            nwc_ratio = (float(ca) - float(cl)) / float(rev)
            out["sales_to_nwc"] = round(max(0.0, nwc_ratio), 4)
        if tax_e is not None and pbt and float(pbt) > 0:
            tr = float(tax_e) / float(pbt)
            out["tax_rate"] = round(min(0.35, max(0.10, tr)), 4)

        cap = out["capex_to_sales"]
        om = operating_margin_pct
        fcf_m = None if fcf is None else (float(fcf) / float(rev) * 100.0)
        # Quality tiers → relative-value multiples (still user-overridable)
        if (cap is not None and cap < 0.05) and (om is not None and om >= 20.0):
            out["ev_ebitda_multiples"] = {"bear": 15.0, "base": 22.0, "bull": 28.0}
            out["quality_tier"] = "asset_light_high_margin"
            out["notes_ko"].append(
                "저Capex·고마진으로 보여 EV/EBITDA 프리셋을 품질 티어(15/22/28)로 올렸습니다."
            )
        elif (cap is not None and cap < 0.08) and (om is not None and om >= 12.0):
            out["ev_ebitda_multiples"] = {"bear": 10.0, "base": 14.0, "bull": 18.0}
            out["quality_tier"] = "quality_compounder"
            out["notes_ko"].append(
                "중간 Capex·양호 마진 → EV/EBITDA 프리셋 10/14/18."
            )
        else:
            out["notes_ko"].append(
                "산업/중후장 기본 배수(6/8/10)를 사용합니다. UI에서 조정하세요."
            )
        if fcf_m is not None and fcf_m >= 20:
            out["notes_ko"].append(
                f"보고 FCF 마진 ~{fcf_m:.1f}%. DCF가 시가보다 낮으면 성장·WACC·해자 프리미엄 가정의 차이일 수 있습니다."
            )
        out["notes_ko"].append(
            "DCF·배수는 시가총액 추종이 목표가 아닙니다. 가정 민감도 밴드입니다."
        )
    return out


def build_seeded_scenarios(
    *,
    operating_margin_pct: float,
    seed: dict[str, Any],
) -> list[dict[str, Any]]:
    """Base/bull/bear with margins from ops and reinvestment from filings."""
    om = float(operating_margin_pct)
    bear_m = max(om - 2.0, om * 0.7) / 100.0
    base_m = om / 100.0
    bull_m = (om + 2.0) / 100.0

    cap = float(seed.get("capex_to_sales") if seed.get("capex_to_sales") is not None else 0.08)
    da = float(seed.get("da_to_sales") if seed.get("da_to_sales") is not None else min(0.05, cap))
    nwc = float(seed.get("sales_to_nwc") if seed.get("sales_to_nwc") is not None else 0.10)
    tax = float(seed.get("tax_rate") if seed.get("tax_rate") is not None else 0.25)
    mult = seed.get("ev_ebitda_multiples") or {"bear": 6.0, "base": 8.0, "bull": 10.0}

    # Keep Capex ≥ DA roughly (maintenance floor); avoid nonsense seeds
    if da > cap:
        da = cap

    return [
        {
            "id": "bear",
            "name_ko": "보수",
            "assumptions": {
                "projection_years": 5,
                "revenue_cagr": 0.0,
                "ebit_margin": bear_m,
                "tax_rate": tax,
                "sales_to_nwc": max(nwc, 0.02),
                "capex_to_sales": min(cap + 0.01, 0.25),
                "da_to_sales": da,
                "wacc": 0.10,
                "terminal_growth": 0.015,
                "ev_ebitda_multiple": float(mult["bear"]),
            },
        },
        {
            "id": "base",
            "name_ko": "기본(공시 시드)",
            "assumptions": {
                "projection_years": 5,
                "revenue_cagr": 0.05,
                "ebit_margin": base_m,
                "tax_rate": tax,
                "sales_to_nwc": nwc,
                "capex_to_sales": cap,
                "da_to_sales": da,
                "wacc": 0.085,
                "terminal_growth": 0.025,
                "ev_ebitda_multiple": float(mult["base"]),
            },
        },
        {
            "id": "bull",
            "name_ko": "낙관",
            "assumptions": {
                "projection_years": 5,
                "revenue_cagr": 0.09,
                "ebit_margin": bull_m,
                "tax_rate": tax,
                "sales_to_nwc": max(0.0, nwc - 0.02),
                "capex_to_sales": max(da, cap - 0.005),
                "da_to_sales": da,
                "wacc": 0.075,
                "terminal_growth": 0.03,
                "ev_ebitda_multiple": float(mult["bull"]),
            },
        },
    ]


def _req(assumptions: dict[str, Any], key: str) -> float:
    if key not in assumptions or assumptions[key] is None:
        raise ValueError(f"missing assumption: {key}")
    return float(assumptions[key])


def fcff_dcf(
    *,
    revenue0: float,
    assumptions: dict[str, Any],
) -> dict[str, Any]:
    """Simple FCFF DCF from revenue0 and user assumptions.

    FCFF_t ≈ EBIT_t*(1-t) + DA_t - Capex_t - ΔNWC_t
    Terminal = FCFF_n*(1+g)/(WACC-g)
    """
    n = int(assumptions.get("projection_years") or 5)
    g_rev = _req(assumptions, "revenue_cagr")
    ebit_m = _req(assumptions, "ebit_margin")
    tax = _req(assumptions, "tax_rate")
    nwc_ratio = _req(assumptions, "sales_to_nwc")
    capex_ratio = _req(assumptions, "capex_to_sales")
    da_ratio = float(assumptions.get("da_to_sales") or 0.0)
    wacc = _req(assumptions, "wacc")
    g = _req(assumptions, "terminal_growth")
    net_debt = float(assumptions.get("net_debt") or 0.0)
    shares = assumptions.get("shares_out")

    if wacc <= g:
        return {
            "ok": False,
            "reason": "wacc_must_exceed_terminal_growth",
            "enterprise_value": None,
            "equity_value": None,
            "value_per_share": None,
        }

    rows: list[dict[str, Any]] = []
    prev_rev = float(revenue0)
    prev_nwc = prev_rev * nwc_ratio
    pv_fcff = 0.0

    for t in range(1, n + 1):
        rev = prev_rev * (1.0 + g_rev)
        ebit = rev * ebit_m
        nopat = ebit * (1.0 - tax)
        da = rev * da_ratio
        capex = rev * capex_ratio
        nwc = rev * nwc_ratio
        delta_nwc = nwc - prev_nwc
        fcff = nopat + da - capex - delta_nwc
        disc = (1.0 + wacc) ** t
        pv = fcff / disc
        pv_fcff += pv
        rows.append(
            {
                "year": t,
                "revenue": round(rev, 2),
                "ebit": round(ebit, 2),
                "fcff": round(fcff, 2),
                "pv_fcff": round(pv, 2),
            }
        )
        prev_rev, prev_nwc = rev, nwc

    fcff_n = rows[-1]["fcff"]
    terminal = fcff_n * (1.0 + g) / (wacc - g)
    pv_terminal = terminal / ((1.0 + wacc) ** n)
    ev = pv_fcff + pv_terminal
    equity = ev - net_debt
    vps = None if not shares else equity / float(shares)

    return {
        "ok": True,
        "model": "fcff_dcf",
        "enterprise_value": round(ev, 2),
        "equity_value": round(equity, 2),
        "value_per_share": None if vps is None else round(vps, 4),
        "pv_explicit_fcff": round(pv_fcff, 2),
        "pv_terminal": round(pv_terminal, 2),
        "terminal_value": round(terminal, 2),
        "projected": rows,
        "assumptions_used": {
            "projection_years": n,
            "revenue_cagr": g_rev,
            "ebit_margin": ebit_m,
            "tax_rate": tax,
            "sales_to_nwc": nwc_ratio,
            "capex_to_sales": capex_ratio,
            "da_to_sales": da_ratio,
            "wacc": wacc,
            "terminal_growth": g,
            "net_debt": net_debt,
            "shares_out": shares,
            "revenue0": revenue0,
        },
    }


def ev_ebitda_value(assumptions: dict[str, Any]) -> dict[str, Any]:
    ebitda = _req(assumptions, "ebitda")
    multiple = _req(assumptions, "ev_ebitda_multiple")
    net_debt = float(assumptions.get("net_debt") or 0.0)
    shares = assumptions.get("shares_out")
    ev = ebitda * multiple
    equity = ev - net_debt
    vps = None if not shares else equity / float(shares)
    return {
        "ok": True,
        "model": "ev_ebitda",
        "enterprise_value": round(ev, 2),
        "equity_value": round(equity, 2),
        "value_per_share": None if vps is None else round(vps, 4),
        "assumptions_used": {
            "ebitda": ebitda,
            "ev_ebitda_multiple": multiple,
            "net_debt": net_debt,
            "shares_out": shares,
        },
    }


def sensitivity_grid(
    *,
    revenue0: float,
    base_assumptions: dict[str, Any],
    wacc_deltas: list[float],
    g_deltas: list[float],
) -> list[dict[str, Any]]:
    grid: list[dict[str, Any]] = []
    for dw in wacc_deltas:
        for dg in g_deltas:
            a = dict(base_assumptions)
            a["wacc"] = float(base_assumptions["wacc"]) + dw
            a["terminal_growth"] = float(base_assumptions["terminal_growth"]) + dg
            res = fcff_dcf(revenue0=revenue0, assumptions=a)
            grid.append(
                {
                    "wacc": a["wacc"],
                    "terminal_growth": a["terminal_growth"],
                    "enterprise_value": res.get("enterprise_value"),
                    "equity_value": res.get("equity_value"),
                    "ok": res.get("ok"),
                }
            )
    return grid


def run_valuation_bundle(
    *,
    revenue0: float,
    ebitda0: float | None,
    net_debt: float | None,
    shares_out: float | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run base/bull/bear (+ optional custom) like shipping stress scenarios."""
    spec = spec or load_valuation_spec()
    scenarios = scenarios or list(spec.get("default_scenarios") or [])
    models_meta = spec.get("models") or {}

    results: list[dict[str, Any]] = []
    for sc in scenarios:
        assum = dict(sc.get("assumptions") or {})
        if net_debt is not None and "net_debt" not in assum:
            assum["net_debt"] = net_debt
        if shares_out is not None and "shares_out" not in assum:
            assum["shares_out"] = shares_out
        if ebitda0 is not None and "ebitda" not in assum:
            assum["ebitda"] = ebitda0

        dcf = fcff_dcf(revenue0=revenue0, assumptions=assum)
        multiple = None
        try:
            multiple = ev_ebitda_value(assum)
        except ValueError:
            multiple = {"ok": False, "reason": "missing_ebitda_or_multiple"}

        results.append(
            {
                "scenario_id": sc.get("id"),
                "name_ko": sc.get("name_ko"),
                "fcff_dcf": dcf,
                "ev_ebitda": multiple,
            }
        )

    # sensitivity on base
    base = next((s for s in scenarios if s.get("id") == "base"), scenarios[0] if scenarios else None)
    sens = []
    if base:
        a = dict(base.get("assumptions") or {})
        if net_debt is not None:
            a.setdefault("net_debt", net_debt)
        sens_cfg = spec.get("sensitivity") or {}
        sens = sensitivity_grid(
            revenue0=revenue0,
            base_assumptions=a,
            wacc_deltas=list(sens_cfg.get("wacc_deltas") or [-0.01, 0, 0.01]),
            g_deltas=list(sens_cfg.get("terminal_growth_deltas") or [-0.005, 0, 0.005]),
        )

    equity_vals = [
        r["fcff_dcf"]["equity_value"]
        for r in results
        if r.get("fcff_dcf", {}).get("ok") and r["fcff_dcf"].get("equity_value") is not None
    ]
    band = None
    if equity_vals:
        low, high = min(equity_vals), max(equity_vals)
        mid = sorted(equity_vals)[len(equity_vals) // 2]
        band = {
            "equity_value_low": low,
            "equity_value_high": high,
            "equity_value_mid": mid,
        }
        if shares_out:
            sh = float(shares_out)
            band["value_per_share_low"] = round(low / sh, 4)
            band["value_per_share_high"] = round(high / sh, 4)
            band["value_per_share_mid"] = round(mid / sh, 4)
            band["shares_out"] = sh

    return {
        "schema_version": "dart-valuation-v1",
        "engine_version": spec.get("engine_version"),
        "disclaimer_ko": spec.get("disclaimer_ko"),
        "models": {
            mid: {
                "label_ko": m.get("label_ko"),
                "pros_ko": m.get("pros_ko"),
                "cons_ko": m.get("cons_ko"),
                "user_assumptions": m.get("user_assumptions"),
            }
            for mid, m in models_meta.items()
        },
        "scenarios": results,
        "value_band": band,
        "sensitivity_wacc_g": sens,
    }
