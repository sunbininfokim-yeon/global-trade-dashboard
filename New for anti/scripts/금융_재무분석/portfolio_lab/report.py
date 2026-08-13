"""Assemble portfolio_analysis_v1 JSON report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .allocate import apply_max_weight_caps, hierarchical_risk_parity
from .covariance import corr_from_cov, ewma_cov, ledoit_wolf_cov
from .explain import (
    build_ui_copy,
    build_ui_copy_basic_en,
    build_ui_copy_basic_ko,
    build_ui_copy_en,
)
from .normalize import MAX_NAMES, build_size_guide
from .risk import portfolio_risk_bundle
from .structure import check_profile, corr_clusters, currency_exposure, stress_windows


DISCLAIMER_KO = (
    "모형 출력은 과거 수익률·공분산 기반 참고 지표이며 투자 권유가 아닙니다. "
    "레버리지·상품은 프록시 가격을 쓸 수 있습니다. 목표 수익률 가정은 사용하지 않습니다."
)

DISCLAIMER_EN = (
    "Model output is a past-returns / covariance reference — not investment advice. "
    "Leveraged products may use proxy prices. No target-return assumption is used."
)


def build_report(
    *,
    portfolio_id: str,
    base_currency: str,
    positions: list[dict[str, Any]],
    rets: pd.DataFrame,
    weights: pd.Series,
    meta: dict[str, Any],
    rf_ann: float = 0.03,
    unresolved: list[str] | None = None,
    risk_profile_id: str = "balanced",
    risk_profile: dict[str, Any] | None = None,
    normalize_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    norm = normalize_meta or {}
    analyzed_gross = None
    signed_positions_value = None
    if positions and all(p.get("value") is not None for p in positions):
        analyzed_gross = sum(abs(float(p["value"])) for p in positions)
        signed_positions_value = sum(float(p["value"]) for p in positions)

    credit_used = float(norm.get("credit_used_krw") or 0.0)
    net_asset_value = norm.get("net_asset_value_krw")
    if net_asset_value is None and signed_positions_value is not None:
        net_asset_value = signed_positions_value - credit_used
    if net_asset_value is not None:
        net_asset_value = float(net_asset_value)
        if net_asset_value <= 0:
            net_asset_value = None

    # Monetary VaR/CVaR must be expressed against NAV, not gross exposure.  The
    # two are equal only for a simple, unleveraged long-only account.
    total_value = net_asset_value

    short_rets = rets.iloc[-252:] if len(rets) >= 60 else rets
    long_rets = rets.copy()

    cov_s = ewma_cov(short_rets, lam=0.94)
    cov_l = ledoit_wolf_cov(long_rets)

    bundle = portfolio_risk_bundle(
        rets,
        weights,
        cov_s,
        cov_l,
        rf_ann=rf_ann,
        total_value=total_value,
    )

    cash_ids = {
        p["instrument"]["id"]
        for p in positions
        if p["instrument"].get("asset_class") == "cash"
        and not p["instrument"].get("fx_as_asset")
    }
    short_ids = {p["instrument"]["id"] for p in positions if float(p.get("weight") or 0) < 0}
    fixed_ids = set(cash_ids) | set(short_ids)

    w0 = weights.reindex(cov_l.index).fillna(0.0)
    long_ids = [i for i in w0.index if i not in fixed_ids and float(w0[i]) >= 0]
    long_budget = float(w0[long_ids].sum()) if long_ids else 0.0
    if len(long_ids) >= 1 and long_budget > 0:
        cov_risky = cov_l.loc[long_ids, long_ids]
        hrp_risky = hierarchical_risk_parity(cov_risky)
        hrp = w0.copy() * 0.0
        for fid in fixed_ids:
            if fid in hrp.index:
                hrp[fid] = w0[fid]
        for rid in long_ids:
            hrp[rid] = float(hrp_risky.get(rid, 0.0)) * long_budget
        scale = long_budget
    else:
        hrp = hierarchical_risk_parity(cov_l)
        scale = float(hrp.sum()) if float(hrp.sum()) else 1.0

    profile = risk_profile or {}
    caps: dict[str, float] = {}
    lev_cap = float(profile.get("leveraged_max") or 0.10)
    single_cap = float(profile.get("single_name_max") or 0.15)
    for p in positions:
        inst = p["instrument"]
        iid = inst["id"]
        if inst.get("leveraged"):
            caps[iid] = min(float(inst.get("max_weight") or lev_cap), lev_cap)
        elif iid in long_ids:
            caps[iid] = single_cap

    if caps and long_ids:
        risky = hrp.reindex(long_ids).fillna(0.0)
        if risky.sum() > 0:
            risky = apply_max_weight_caps(risky, caps)
            risky = risky / risky.sum() * scale
            hrp = w0.copy() * 0.0
            for fid in fixed_ids:
                if fid in hrp.index:
                    hrp[fid] = w0[fid]
            hrp = hrp.add(risky, fill_value=0.0)

    hrp = hrp.reindex(weights.index).fillna(0.0)
    delta = hrp - weights.reindex(hrp.index).fillna(0.0)

    corr_s = corr_from_cov(cov_s)
    pairs = []
    cols = list(corr_s.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs.append(
                {
                    "a": cols[i],
                    "b": cols[j],
                    "corr": float(corr_s.iloc[i, j]),
                    "a_ko": None,
                    "b_ko": None,
                }
            )
    pairs.sort(key=lambda x: abs(x["corr"]), reverse=True)

    names = {p["instrument"]["id"]: p["instrument"]["name_ko"] for p in positions}
    for row in pairs:
        row["a_ko"] = names.get(row["a"], row["a"])
        row["b_ko"] = names.get(row["b"], row["b"])

    def labeled(series: pd.Series) -> dict[str, float]:
        return {names.get(k, k): float(v) for k, v in series.items()}

    clusters = corr_clusters(corr_s, weights, names)
    fx = currency_exposure(positions)
    stress = stress_windows(rets, weights)
    profile_check = check_profile(
        positions,
        weights,
        bundle["risk"],
        profile,
        base_currency=base_currency,
    ) if profile else {
        "ok": True,
        "breaches_ko": [],
        "breaches_en": [],
    }

    notes = [
        f"투자 성향: {profile.get('label_ko', risk_profile_id)} — {profile.get('blurb_ko', '')}",
        "원화 현금·공매도 비중은 고정하고, 롱 위험자산만 위험을 고르게 나누는 방향(HRP)입니다.",
        "목표 수익률은 사용하지 않습니다 (기대수익 가정 없음).",
    ]
    notes_en = [
        (
            f"Risk style: {profile.get('label_en') or profile.get('label_ko', risk_profile_id)} — "
            f"{profile.get('blurb_en') or profile.get('blurb_ko', '')}"
        ),
        "KRW cash and short sleeves stay flat; only the long risky sleeve is rebalanced toward even risk (HRP).",
        "No target return is used (no expected-return assumption).",
    ]
    for b in profile_check.get("breaches_ko") or []:
        notes.append(f"성향 점검: {b}")
    for b in profile_check.get("breaches_en") or []:
        notes_en.append(f"Profile check: {b}")
    top_up = delta.sort_values(ascending=False).head(3)
    top_down = delta.sort_values(ascending=True).head(3)
    for k, v in top_up.items():
        if v > 0.01:
            notes.append(f"늘리는 쪽 후보: '{names.get(k, k)}' (+{v:.1%}p)")
            notes_en.append(f"Add candidate: '{names.get(k, k)}' (+{v:.1%}p)")
    for k, v in top_down.items():
        if v < -0.01:
            notes.append(f"줄이는 쪽 후보: '{names.get(k, k)}' ({v:.1%}p)")
            notes_en.append(f"Trim candidate: '{names.get(k, k)}' ({v:.1%}p)")
    if any(p["instrument"].get("leveraged") for p in positions):
        notes.append("레버리지 ETF는 비중보다 위험을 더 키웁니다. 장기에는 배수만큼 수익이 안 나올 수 있습니다.")
        notes_en.append(
            "Leveraged ETFs amplify risk beyond their weight; long-run returns may not match the multiple."
        )
    if meta.get("proxies"):
        notes.append("금·일본국채·일부 레버리지는 ETF/현물 프록시로 계산했습니다.")
        notes_en.append("Gold, JGBs, and some leverage sleeves use ETF/spot proxies.")

    size_guide = norm.get("size_guide")
    if size_guide is None and total_value is not None:
        size_guide = build_size_guide(float(total_value), n_names=len(positions))
    elif size_guide is not None:
        # Refresh vs_actual against resolved unique count (after id merge).
        size_guide = dict(size_guide)
        size_guide["vs_actual"] = {
            "n_names": len(positions),
            "status": (
                "too_few"
                if len(positions) < int(size_guide.get("names_min") or 0)
                else (
                    "too_many"
                    if len(positions) > int(size_guide.get("names_max") or 10**9)
                    else "ok"
                )
            ),
        }
    for n in norm.get("notes_ko") or []:
        notes.append(n)
    for n in norm.get("notes_en") or []:
        notes_en.append(n)
    if size_guide:
        sg_status = (size_guide.get("vs_actual") or {}).get("status")
        n_act = (size_guide.get("vs_actual") or {}).get("n_names")
        lo, hi = size_guide.get("names_min"), size_guide.get("names_max")
        if sg_status == "too_many":
            notes.append(
                f"규모 가이드({size_guide.get('label_ko')}): 현재 {n_act}종 · 권장 {lo}–{hi} "
                f"— 통합·ETF 축소를 검토하세요."
            )
            notes_en.append(
                f"Size guide ({size_guide.get('label_en')}): {n_act} names vs "
                f"suggested {lo}–{hi} — consider consolidating."
            )
        elif sg_status == "too_few":
            notes.append(
                f"규모 가이드({size_guide.get('label_ko')}): 현재 {n_act}종 · 권장 {lo}–{hi} "
                f"— 분산(자산군·ETF) 여지를 볼 수 있습니다."
            )
            notes_en.append(
                f"Size guide ({size_guide.get('label_en')}): {n_act} names vs "
                f"suggested {lo}–{hi} — room to diversify across sleeves/ETFs."
            )

    base_ccy = str(base_currency).upper()
    base_cash_value = 0.0
    foreign_cash_value = 0.0
    for p in positions:
        inst = p["instrument"]
        if inst.get("asset_class") != "cash":
            continue
        value = float(p.get("value") or 0.0)
        if str(inst.get("currency") or "").upper() == base_ccy and not inst.get("fx_as_asset"):
            base_cash_value += max(value, 0.0)
        else:
            foreign_cash_value += abs(value)

    gross_of_nav = (
        float(analyzed_gross / net_asset_value)
        if analyzed_gross is not None and net_asset_value is not None and net_asset_value > 0
        else None
    )
    submitted_gross = norm.get("gross_exposure_krw")
    analysis_gross_coverage = (
        float(analyzed_gross / float(submitted_gross))
        if analyzed_gross is not None and submitted_gross not in (None, 0)
        else None
    )
    if credit_used > 0:
        notes.append(
            f"신용·미수 {credit_used:,.0f}원은 순자산과 총노출을 분리해 계산했습니다. "
            "금액 VaR은 총노출이 아니라 순자산 기준입니다."
        )
        notes_en.append(
            f"Credit/margin debt of {credit_used:,.0f} is separated from NAV and gross exposure; "
            "money VaR is NAV-based, not gross-based."
        )
    if analysis_gross_coverage is not None and analysis_gross_coverage < 0.999999:
        notes.append(
            f"상위 {MAX_NAMES}개만 분석되어 제출 총노출의 약 {analysis_gross_coverage:.1%}만 반영합니다. "
            "포트폴리오 전체 VaR로 해석하면 안 됩니다."
        )
        notes_en.append(
            f"Only the top {MAX_NAMES} lines are analyzed ({analysis_gross_coverage:.1%} of submitted gross exposure); "
            "do not treat VaR as whole-portfolio VaR."
        )

    shrink = float(getattr(cov_l, "attrs", {}).get("shrinkage", np.nan))

    report: dict[str, Any] = {
        "schema_version": "portfolio_analysis_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_currency": base_currency,
        "portfolio_id": portfolio_id,
        "disclaimer_ko": DISCLAIMER_KO,
        "disclaimer_en": DISCLAIMER_EN,
        "risk_profile_id": risk_profile_id,
        # Full profile object (cash bands + footnotes) for hover/tooltip UI.
        "risk_profile_meta": profile,
        "risk_profile_footnotes": {
            "cash_footnote_ko": profile.get("cash_footnote_ko"),
            "cash_footnote_en": profile.get("cash_footnote_en"),
            "why_cash_band_ko": profile.get("why_cash_band_ko"),
            "why_cash_band_en": profile.get("why_cash_band_en"),
            "methodology_note_ko": profile.get("methodology_note_ko"),
            "methodology_note_en": profile.get("methodology_note_en"),
            "cash_min": profile.get("cash_min"),
            "cash_max": profile.get("cash_max"),
            "gross_exposure_max": profile.get("gross_exposure_max"),
            "var_10d_budget": profile.get("var_10d_budget"),
        },
        "accounting": {
            "net_asset_value": net_asset_value,
            "gross_exposure": analyzed_gross,
            "gross_exposure_of_nav": gross_of_nav,
            "signed_positions_value": signed_positions_value,
            "credit_used": credit_used,
            "basis_ko": "금액 VaR·현금 밴드의 분모는 순자산(NAV)입니다. 총노출은 별도로 표시합니다.",
            "basis_en": "Money VaR and cash-band ratios use net asset value (NAV); gross exposure is separate.",
        },
        "cash_breakdown": {
            "base_currency": base_ccy,
            "base_cash_value": base_cash_value,
            "foreign_cash_value": foreign_cash_value,
            "base_cash_weight_of_nav": (
                float(base_cash_value / net_asset_value) if net_asset_value else None
            ),
            "foreign_cash_weight_of_nav": (
                float(foreign_cash_value / net_asset_value) if net_asset_value else None
            ),
            "policy_ko": "성향 현금 밴드는 기준통화 현금에만 적용합니다. 외화 현금은 환율 위험 자산으로 별도 표시합니다.",
            "policy_en": "Risk-profile cash bands apply only to base-currency cash. Foreign cash is shown separately as FX exposure.",
        },
        "positions": [
            {
                "id": p["instrument"]["id"],
                "name_ko": p["instrument"]["name_ko"],
                "yahoo": p["instrument"].get("yahoo"),
                "asset_class": p["instrument"]["asset_class"],
                "currency": p["instrument"].get("currency"),
                "value": p.get("value"),
                "weight": p["weight"],
                "side": p.get("side") or ("short" if float(p.get("weight") or 0) < 0 else "long"),
                "leveraged": p["instrument"].get("leveraged", False),
                "proxy": p["instrument"].get("proxy", False),
            }
            for p in positions
        ],
        "performance": {
            **bundle["performance"],
            "total_value": total_value,
            "net_asset_value": net_asset_value,
            "gross_exposure": analyzed_gross,
            "horizon_note_ko": "1Y는 오늘 기준 지난 약 1년(거래일) 누적입니다. 달력 연도(1~12월) 대비가 아닙니다.",
            "horizon_note_en": (
                "1Y is cumulative over roughly the past year of trading days from today — "
                "not calendar-year YoY."
            ),
        },
        "risk": bundle["risk"],
        "structure": {
            "risk_contribution": {
                names.get(k, k): float(v) for k, v in bundle["risk_contribution"].items()
            },
            "clusters": clusters,
            "currency_exposure": fx,
            "corr_short_top_pairs": pairs[:12],
            "cov_long_shrinkage": None if np.isnan(shrink) else shrink,
        },
        "stress": stress,
        "profile_check": profile_check,
        "advice": {
            "method": "HRP_long_risky_sleeve",
            "reference": "Lopez de Prado (2016) Hierarchical Risk Parity; Ledoit-Wolf covariance",
            "cash_policy": "flat_cash_and_shorts_fixed",
            "risk_profile": risk_profile_id,
            "no_expected_return": True,
            "current_weights": labeled(weights),
            "target_weights": labeled(hrp),
            "delta_weights": labeled(delta),
            "notes_ko": notes,
            "notes_en": notes_en,
            "constraints_applied": caps,
        },
        "data_quality": {
            "unresolved_queries": unresolved or [],
            "proxies": meta.get("proxies") or [],
            "errors": meta.get("errors") or [],
            "price_sources": meta.get("price_sources") or {},
            "n_obs": int(len(rets)),
            "start": str(rets.index.min().date()) if len(rets) else None,
            "end": str(rets.index.max().date()) if len(rets) else None,
            "max_names": int(norm.get("max_names") or MAX_NAMES),
            "residual_cash_added": norm.get("residual_cash_added"),
            "total_was_inferred": norm.get("total_was_inferred"),
            "analysis_gross_coverage": analysis_gross_coverage,
            "truncated_positions": norm.get("truncated_positions") or [],
        },
        "size_guide": size_guide,
        "positions_truncated_ko": norm.get("positions_truncated_ko"),
        "positions_truncated_en": norm.get("positions_truncated_en"),
        "input_normalize": {
            "max_names": int(norm.get("max_names") or MAX_NAMES),
            "aum_krw": norm.get("aum_krw"),
            "net_asset_value_krw": norm.get("net_asset_value_krw"),
            "gross_exposure_krw": norm.get("gross_exposure_krw"),
            "signed_positions_value_krw": norm.get("signed_positions_value_krw"),
            "credit_used_krw": credit_used,
            "total_was_inferred": norm.get("total_was_inferred"),
            "residual_cash_added": norm.get("residual_cash_added") or 0.0,
            "truncated_positions": norm.get("truncated_positions") or [],
        },
    }
    report["ui_copy_ko"] = build_ui_copy(
        report,
        profile=profile,
        profile_id=risk_profile_id,
    )
    report["ui_copy_en"] = build_ui_copy_en(
        report,
        profile=profile,
        profile_id=risk_profile_id,
    )
    report["ui_copy_basic_ko"] = build_ui_copy_basic_ko(
        report,
        profile=profile,
        profile_id=risk_profile_id,
    )
    report["ui_copy_basic_en"] = build_ui_copy_basic_en(
        report,
        profile=profile,
        profile_id=risk_profile_id,
    )
    return report
