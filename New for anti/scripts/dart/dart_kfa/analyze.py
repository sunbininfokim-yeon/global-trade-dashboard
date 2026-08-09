"""End-to-end analyze: payload → company JSON (dart-company-v1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import ENGINE_VERSION
from .accounts import amounts_only, load_accounts_map, resolve_accounts
from .industry import apply_industry_layer
from .ma_metrics import compute_ma_metrics
from .metrics import compute_metrics, load_metrics_spec
from .narrative import narratives_ko
from .validate import validate_accounts
from .fundamental_pack import attach_market_to_pack, build_fundamental_pack
from .valuation import (
    build_seeded_scenarios,
    run_valuation_bundle,
    seed_from_statements,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _meta_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    r0 = rows[0]
    return {
        "corp_code": r0.get("corp_code"),
        "stock_code": (r0.get("stock_code") or "").strip() or None,
        "reprt_code": r0.get("reprt_code"),
        "bsns_year": r0.get("bsns_year"),
        "fs_div": r0.get("fs_div"),
        "currency": r0.get("currency"),
    }


def _mv(metrics: dict[str, Any], mid: str) -> float | None:
    cell = metrics.get(mid) or {}
    v = cell.get("value")
    return float(v) if v is not None else None


def analyze_rows(
    rows: list[dict[str, Any]],
    *,
    corp: dict[str, Any] | None = None,
    accounts_map: dict[str, Any] | None = None,
    metrics_spec: dict[str, Any] | None = None,
    include_valuation: bool = True,
    shares_out: float | None = None,
) -> dict[str, Any]:
    amap = accounts_map or load_accounts_map()
    mspec = metrics_spec or load_metrics_spec()

    resolved = resolve_accounts(rows, amap)
    current = amounts_only(resolved, "value")
    prior = amounts_only(resolved, "prior")
    prior2 = amounts_only(resolved, "prior2")

    gate = validate_accounts(current)
    metrics = compute_metrics(current, mspec)

    for mid in list(metrics.keys()):
        series = [
            compute_metrics(prior2, mspec).get(mid, {}).get("value"),
            compute_metrics(prior, mspec).get(mid, {}).get("value"),
            metrics[mid].get("value"),
        ]
        if any(v is not None for v in series):
            metrics[mid]["trend_3y"] = series

    industry = apply_industry_layer(corp=corp, metrics=metrics, amounts=current)
    ma = compute_ma_metrics(current, metrics)

    # Current operating margin for UI assumption defaults
    om = _mv(metrics, "operating_margin")
    peer_net = None
    try:
        peer_net = ((industry.get("bok_peer") or {}).get("row") or {}).get("net_margin")
    except Exception:  # noqa: BLE001
        peer_net = None

    fcf_v = (ma.get("fcf") or {}).get("value")
    val_seed = seed_from_statements(
        current,
        operating_margin_pct=om,
        fcf=float(fcf_v) if fcf_v is not None else None,
    )
    assumption_defaults = {
        "current_operating_margin_pct": om,
        "bok_peer_net_margin_pct": peer_net,
        "seeded_from_statements": {
            "capex_to_sales": val_seed.get("capex_to_sales"),
            "da_to_sales": val_seed.get("da_to_sales"),
            "sales_to_nwc": val_seed.get("sales_to_nwc"),
            "tax_rate": val_seed.get("tax_rate"),
            "quality_tier": val_seed.get("quality_tier"),
            "ev_ebitda_multiples": val_seed.get("ev_ebitda_multiples"),
        },
        "preset_suggestions": {
            "bear": None if om is None else round(max(om - 2.0, om * 0.7), 2),
            "base": om,
            "bull": None if om is None else round(om + 2.0, 2),
            "unit": "pct",
            "note_ko": "마진·Capex·DA·세금은 공시에서 시드. DCF는 시가 추종이 아님. "
            "한은 peer 순이익률은 참고용(영업이익률과 정의 다름).",
        },
        "notes_ko": val_seed.get("notes_ko") or [],
    }

    valuation = None
    if include_valuation and current.get("REVENUE") is not None:
        ebitda = (ma.get("ebitda_proxy") or {}).get("value")
        net_debt = (ma.get("net_debt") or {}).get("value")
        if net_debt is None:
            net_debt = (ma.get("net_debt_incl_lease") or {}).get("value")
        if net_debt is None:
            net_debt = (ma.get("net_debt_proxy") or {}).get("value")
        custom_scenarios = None
        if om is not None:
            custom_scenarios = build_seeded_scenarios(
                operating_margin_pct=om,
                seed=val_seed,
            )
        valuation = run_valuation_bundle(
            revenue0=float(current["REVENUE"]),
            ebitda0=float(ebitda) if ebitda is not None else None,
            net_debt=float(net_debt) if net_debt is not None else 0.0,
            shares_out=float(shares_out) if shares_out is not None else None,
            scenarios=custom_scenarios,
        )

    meta = _meta_from_rows(rows)
    corp_out = {
        "code": (corp or {}).get("code") or meta.get("stock_code"),
        "corp_code": (corp or {}).get("corp_code") or meta.get("corp_code"),
        "name": (corp or {}).get("name"),
        "industry": (corp or {}).get("industry"),
        "industry_kit": industry.get("industry_kit"),
    }

    year = None
    if meta.get("bsns_year"):
        try:
            year = int(meta["bsns_year"])
        except (TypeError, ValueError):
            year = meta["bsns_year"]

    parse_status = gate["parse_status"]
    narrative = narratives_ko(
        metrics,
        parse_status=parse_status,
        industry=industry,
        ma=ma,
    )

    period = {
        "year": year,
        "reprt": meta.get("reprt_code") or (corp or {}).get("reprt"),
        "fs_div": meta.get("fs_div") or (corp or {}).get("fs_div"),
    }

    fundamental_pack = build_fundamental_pack(
        corp=corp_out,
        period=period,
        metrics=metrics,
        ma=ma,
        industry=industry,
        valuation=valuation,
        market=None,
        amounts_current=current,
        amounts_prior=prior,
        amounts_prior2=prior2,
    )

    return {
        "schema_version": "dart-company-v1",
        "generated_at": _now_iso(),
        "engine_version": mspec.get("engine_version") or ENGINE_VERSION,
        "corp": corp_out,
        "period": period,
        "parse_status": parse_status,
        "validation": gate,
        "accounts": {
            k: {
                "value": v.get("value"),
                "match": v.get("match"),
                "account_nm": v.get("account_nm"),
                "reason": v.get("reason"),
            }
            for k, v in resolved.items()
        },
        "metrics": metrics,
        "industry": industry,
        "ma_metrics": ma,
        "assumption_defaults": assumption_defaults,
        "valuation": valuation,
        "fundamental_pack": fundamental_pack,
        "shares_out": float(shares_out) if shares_out is not None else None,
        "scores": {},
        "macro_beta": {},
        "narrative": narrative,
        "disclaimer_ko": "본 산출물은 공시 숫자·사용자 가정 모형이며 투자 권유가 아닙니다.",
    }


def analyze_payload(
    payload: dict[str, Any],
    *,
    corp: dict[str, Any] | None = None,
    include_valuation: bool = True,
    shares_out: float | None = None,
) -> dict[str, Any]:
    from .fetch import rows_from_payload

    rows = rows_from_payload(payload)
    return analyze_rows(
        rows,
        corp=corp,
        include_valuation=include_valuation,
        shares_out=shares_out,
    )


def universe_summary(company: dict[str, Any]) -> dict[str, Any]:
    """Compact row for dart_universe_v1 screener snapshot."""
    metrics = company.get("metrics") or {}
    ma = company.get("ma_metrics") or {}
    industry = company.get("industry") or {}
    band = (company.get("valuation") or {}).get("value_band")

    def v(mid: str, bag: dict[str, Any] | None = None) -> float | None:
        cell = (bag or metrics).get(mid) or {}
        return cell.get("value")

    return {
        "corp": company.get("corp"),
        "period": company.get("period"),
        "parse_status": company.get("parse_status"),
        "industry_kit": industry.get("industry_kit"),
        "flags": [f.get("id") for f in industry.get("flags") or []],
        "metrics": {
            "current_ratio": v("current_ratio"),
            "debt_ratio": v("debt_ratio"),
            "roe": v("roe"),
            "roa": v("roa"),
            "operating_margin": v("operating_margin"),
            "earnings_quality": v("earnings_quality"),
            "fcf": v("fcf", ma),
            "net_debt_to_ebitda": v("net_debt_to_ebitda", ma),
        },
        "value_band": band,
        "engine_version": company.get("engine_version"),
    }
