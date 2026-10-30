"""Assumption-driven valuation (shipping-scenario style). Pure functions."""

from __future__ import annotations

import json
import math
from datetime import date
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
    """Return statement-derived valuation inputs without inventing forecasts.

    The filing can support historical Capex, D&A, working-capital and tax
    ratios.  It cannot support a company-specific WACC, terminal growth or
    peer multiple by itself.  Those inputs are therefore deliberately absent.
    """
    rev = amounts.get("REVENUE")
    out: dict[str, Any] = {
        "capex_to_sales": None,
        "da_to_sales": None,
        "operating_nwc_to_sales": None,
        "nwc_to_sales_proxy": None,
        "tax_rate": None,
        "ev_ebitda_multiples": None,
        "quality_tier": None,
        "assumption_sources": {},
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
            out["assumption_sources"]["capex_to_sales"] = "filing:capex/revenue"
        if da is not None:
            out["da_to_sales"] = round(abs(float(da)) / float(rev), 4)
            out["assumption_sources"]["da_to_sales"] = "filing:depreciation/revenue"
        if ca is not None and cl is not None:
            # Preserve negative NWC.  Flooring it would fabricate reinvestment.
            nwc_ratio = (float(ca) - float(cl)) / float(rev)
            out["nwc_to_sales_proxy"] = round(nwc_ratio, 4)
            out["assumption_sources"]["nwc_to_sales_proxy"] = (
                "proxy:filing_(current_assets-current_liabilities)/revenue_not_operating_nwc"
            )
        if tax_e is not None and pbt and float(pbt) > 0:
            tr = float(tax_e) / float(pbt)
            # Do not clamp a reported effective rate into a preferred range.
            if 0.0 <= tr <= 1.0:
                out["tax_rate"] = round(tr, 4)
                out["assumption_sources"]["tax_rate"] = "filing:income_tax_expense/profit_before_tax"

        out["notes_ko"].append(
            "공시에서 역산한 재투자·세율 시드만 제공합니다. WACC·영구성장·피어 배수는 자동 추정하지 않습니다."
        )
    return out


def build_seeded_scenarios(
    *,
    operating_margin_pct: float,
    seed: dict[str, Any],
    explicit_assumptions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Validate caller scenarios and optionally accept filing-derived seeds.

    Historical statement ratios may seed the model.  Forecast growth, WACC
    and terminal growth must be caller supplied; an empty list means the
    model is not ready and must not be rendered as a valuation result.
    """
    explicit = explicit_assumptions or {}
    raw_scenarios = explicit.get("scenarios")
    if raw_scenarios is None:
        raw_scenarios = [{"id": "base", "name_ko": "사용자 기본", "assumptions": explicit}]
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        return []

    required = (
        "projection_years", "revenue_cagr", "ebit_margin", "tax_rate",
        "operating_nwc_to_sales", "capex_to_sales", "da_to_sales", "wacc", "terminal_growth",
    )
    accepted_seed_keys = {"capex_to_sales", "da_to_sales", "tax_rate"}
    accept_seed = explicit.get("accept_historical_seed") is True
    scenarios: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_scenarios):
        if not isinstance(raw, dict):
            return []
        assumptions = dict(raw.get("assumptions") or {})
        sources = {key: "caller_input" for key in assumptions}
        if accept_seed:
            for key in accepted_seed_keys:
                if assumptions.get(key) is None and seed.get(key) is not None:
                    assumptions[key] = seed[key]
                    sources[key] = (seed.get("assumption_sources") or {}).get(key, "filing_historical_seed")
        if any(assumptions.get(key) is None for key in required):
            return []
        try:
            years = int(assumptions["projection_years"])
            wacc = float(assumptions["wacc"])
            terminal_growth = float(assumptions["terminal_growth"])
        except (TypeError, ValueError):
            return []
        if not 1 <= years <= 20 or not math.isfinite(wacc) or not math.isfinite(terminal_growth):
            return []
        if wacc <= terminal_growth or terminal_growth > 0.03:
            return []
        assumptions["assumption_sources"] = sources
        assumptions["reported_current_operating_margin_pct"] = operating_margin_pct
        scenarios.append(
            {
                "id": raw.get("id") or f"scenario_{index + 1}",
                "name_ko": raw.get("name_ko") or "사용자 시나리오",
                "assumptions": assumptions,
            }
        )
    return scenarios


def _req(assumptions: dict[str, Any], key: str) -> float:
    if key not in assumptions or assumptions[key] is None:
        raise ValueError(f"missing assumption: {key}")
    value = float(assumptions[key])
    if not math.isfinite(value):
        raise ValueError(f"non-finite assumption: {key}")
    return value


def _verified_share_context(assumptions: dict[str, Any]) -> tuple[float | None, list[str]]:
    """Return point-in-time shares only when their identity is auditable."""
    reasons: list[str] = []
    raw_shares = assumptions.get("shares_out")
    try:
        shares = float(raw_shares) if raw_shares is not None else None
    except (TypeError, ValueError):
        shares = None
    if shares is None or not math.isfinite(shares) or shares <= 0:
        reasons.append("missing:positive_point_in_time_shares")

    basis = assumptions.get("share_basis")
    if basis not in {"point_in_time_basic", "point_in_time_diluted"}:
        reasons.append("missing:point_in_time_share_basis")
    for key in ("share_source_ref", "share_class", "dilution_policy"):
        if not str(assumptions.get(key) or "").strip():
            reasons.append(f"missing:{key}")
    as_of = str(assumptions.get("share_as_of") or "").strip()
    try:
        date.fromisoformat(as_of)
    except ValueError:
        reasons.append("missing:valid_share_as_of")
    return (shares if not reasons else None), reasons


def fcff_dcf(
    *,
    revenue0: float,
    assumptions: dict[str, Any],
) -> dict[str, Any]:
    """Simple FCFF DCF from revenue0 and user assumptions.

    FCFF_t ≈ EBIT_t*(1-t) + DA_t - Capex_t - ΔNWC_t
    Terminal = FCFF_n*(1+g)/(WACC-g)
    """
    revenue0 = float(revenue0)
    if not math.isfinite(revenue0) or revenue0 <= 0:
        raise ValueError("revenue0_must_be_positive_and_finite")
    n = int(_req(assumptions, "projection_years"))
    g_rev = _req(assumptions, "revenue_cagr")
    ebit_m = _req(assumptions, "ebit_margin")
    tax = _req(assumptions, "tax_rate")
    nwc_ratio = _req(assumptions, "operating_nwc_to_sales")
    capex_ratio = _req(assumptions, "capex_to_sales")
    da_ratio = _req(assumptions, "da_to_sales")
    wacc = _req(assumptions, "wacc")
    g = _req(assumptions, "terminal_growth")
    net_debt_raw = assumptions.get("net_debt")
    net_debt = None if net_debt_raw is None else float(net_debt_raw)
    if net_debt is not None and not math.isfinite(net_debt):
        raise ValueError("net_debt_must_be_finite")
    shares, share_reasons = _verified_share_context(assumptions)

    if not 1 <= n <= 20:
        raise ValueError("projection_years_out_of_range")
    if not (-1.0 < g_rev <= 1.0):
        raise ValueError("revenue_cagr_out_of_range")
    if not (-1.0 <= ebit_m <= 1.0):
        raise ValueError("ebit_margin_out_of_range")
    if not (0.0 <= tax <= 1.0):
        raise ValueError("tax_rate_out_of_range")
    if not (-2.0 <= nwc_ratio <= 2.0):
        raise ValueError("operating_nwc_to_sales_out_of_range")
    if not (0.0 <= capex_ratio <= 2.0 and 0.0 <= da_ratio <= 2.0):
        raise ValueError("capex_or_da_ratio_out_of_range")
    if not (0.0 < wacc <= 1.0 and -1.0 < g <= 0.03):
        raise ValueError("wacc_or_terminal_growth_out_of_range")

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
    equity = None if net_debt is None else ev - net_debt
    vps = None if equity is None or shares is None else equity / shares
    reasons: list[str] = []
    if net_debt is None:
        reasons.append("missing:verified_net_debt_for_equity_value")
    reasons.extend(share_reasons)

    return {
        "ok": True,
        "model": "fcff_dcf",
        "enterprise_value": round(ev, 2),
        "equity_value": None if equity is None else round(equity, 2),
        "value_per_share": None if vps is None else round(vps, 4),
        "reasons": reasons,
        "pv_explicit_fcff": round(pv_fcff, 2),
        "pv_terminal": round(pv_terminal, 2),
        "terminal_value": round(terminal, 2),
        "projected": rows,
        "assumptions_used": {
            "projection_years": n,
            "revenue_cagr": g_rev,
            "ebit_margin": ebit_m,
            "tax_rate": tax,
            "operating_nwc_to_sales": nwc_ratio,
            "capex_to_sales": capex_ratio,
            "da_to_sales": da_ratio,
            "wacc": wacc,
            "terminal_growth": g,
            "net_debt": net_debt,
            "shares_out": assumptions.get("shares_out"),
            "share_basis": assumptions.get("share_basis"),
            "share_source_ref": assumptions.get("share_source_ref"),
            "share_as_of": assumptions.get("share_as_of"),
            "share_class": assumptions.get("share_class"),
            "dilution_policy": assumptions.get("dilution_policy"),
            "revenue0": revenue0,
        },
    }


def ev_ebitda_value(assumptions: dict[str, Any]) -> dict[str, Any]:
    ebitda = _req(assumptions, "ebitda")
    multiple = _req(assumptions, "ev_ebitda_multiple")
    if ebitda <= 0 or multiple <= 0:
        raise ValueError("ebitda_and_multiple_must_be_positive")
    net_debt_raw = assumptions.get("net_debt")
    net_debt = None if net_debt_raw is None else float(net_debt_raw)
    shares, share_reasons = _verified_share_context(assumptions)
    ev = ebitda * multiple
    equity = None if net_debt is None else ev - net_debt
    vps = None if equity is None or shares is None else equity / shares
    return {
        "ok": True,
        "model": "ev_ebitda",
        "enterprise_value": round(ev, 2),
        "equity_value": None if equity is None else round(equity, 2),
        "value_per_share": None if vps is None else round(vps, 4),
        "reasons": (
            (["missing:verified_net_debt_for_equity_value"] if net_debt is None else [])
            + share_reasons
        ),
        "assumptions_used": {
            "ebitda": ebitda,
            "ev_ebitda_multiple": multiple,
            "net_debt": net_debt,
            "shares_out": assumptions.get("shares_out"),
            "share_basis": assumptions.get("share_basis"),
            "share_source_ref": assumptions.get("share_source_ref"),
            "share_as_of": assumptions.get("share_as_of"),
            "share_class": assumptions.get("share_class"),
            "dilution_policy": assumptions.get("dilution_policy"),
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
    share_basis: str | None = None,
    share_metadata: dict[str, Any] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run only caller-supplied scenarios; never invent a valuation preset."""
    spec = spec or load_valuation_spec()
    models_meta = spec.get("models") or {}
    if not scenarios:
        return {
            "schema_version": "dart-valuation-v2",
            "status": "inputs_required",
            "reason": "missing:explicit_forecast_wacc_terminal_growth",
            "required_inputs": [
                "projection_years", "revenue_cagr", "ebit_margin", "tax_rate", "operating_nwc_to_sales",
                "capex_to_sales", "da_to_sales", "wacc", "terminal_growth",
            ],
            "models": {},
            "scenarios": [],
            "value_band": None,
            "sensitivity_wacc_g": [],
        }

    results: list[dict[str, Any]] = []
    shared_share_inputs = dict(share_metadata or {})
    if shares_out is not None:
        shared_share_inputs.setdefault("shares_out", shares_out)
    if share_basis is not None:
        shared_share_inputs.setdefault("share_basis", share_basis)
    for sc in scenarios:
        assum = dict(sc.get("assumptions") or {})
        if net_debt is not None and "net_debt" not in assum:
            assum["net_debt"] = net_debt
        for key, value in shared_share_inputs.items():
            assum.setdefault(key, value)
        if ebitda0 is not None and "ebitda" not in assum:
            assum["ebitda"] = ebitda0

        try:
            dcf = fcff_dcf(revenue0=revenue0, assumptions=assum)
        except (TypeError, ValueError) as exc:
            dcf = {
                "ok": False,
                "reason": f"invalid_or_missing_explicit_assumption:{exc}",
                "enterprise_value": None,
                "equity_value": None,
                "value_per_share": None,
            }
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
        try:
            sens = sensitivity_grid(
                revenue0=revenue0,
                base_assumptions=a,
                wacc_deltas=list(sens_cfg.get("wacc_deltas") or [-0.01, 0, 0.01]),
                g_deltas=list(sens_cfg.get("terminal_growth_deltas") or [-0.005, 0, 0.005]),
            )
        except (KeyError, TypeError, ValueError):
            sens = []

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
        verified_shares, _ = _verified_share_context(shared_share_inputs)
        if verified_shares is not None:
            sh = verified_shares
            band["value_per_share_low"] = round(low / sh, 4)
            band["value_per_share_high"] = round(high / sh, 4)
            band["value_per_share_mid"] = round(mid / sh, 4)
            band["shares_out"] = sh
            band["share_basis"] = shared_share_inputs.get("share_basis")
            band["share_source_ref"] = shared_share_inputs.get("share_source_ref")
            band["share_as_of"] = shared_share_inputs.get("share_as_of")
            band["share_class"] = shared_share_inputs.get("share_class")
            band["dilution_policy"] = shared_share_inputs.get("dilution_policy")

    successful_dcf = any((row.get("fcff_dcf") or {}).get("ok") for row in results)
    return {
        "schema_version": "dart-valuation-v2",
        "status": "scenario" if successful_dcf else "blocked_quality",
        "reason": None if successful_dcf else "invalid:no_successful_explicit_fcff_scenario",
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
