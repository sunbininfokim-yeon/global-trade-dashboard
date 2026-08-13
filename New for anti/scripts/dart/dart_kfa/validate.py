"""L1b — balance-sheet identity and unit sanity gates."""

from __future__ import annotations

from typing import Any


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


def validate_accounts(
    amounts: dict[str, float | None],
    *,
    tolerance: float = 0.001,
) -> dict[str, Any]:
    """Return parse_status + list of check results.

    Assets ≈ Liabilities + Equity (default 0.1% relative tolerance).
    """
    checks: list[dict[str, Any]] = []
    assets = _f(amounts.get("TOTAL_ASSETS"))
    liab = _f(amounts.get("TOTAL_LIABILITIES"))
    equity = _f(amounts.get("EQUITY"))
    ca = _f(amounts.get("CURRENT_ASSETS"))
    cl = _f(amounts.get("CURRENT_LIABILITIES"))

    identity_ok = None
    if assets is not None and liab is not None and equity is not None:
        rhs = liab + equity
        if assets == 0 and rhs == 0:
            identity_ok = True
            rel = 0.0
        else:
            denom = max(abs(assets), abs(rhs), 1.0)
            rel = abs(assets - rhs) / denom
            identity_ok = rel <= tolerance
        checks.append(
            {
                "id": "assets_eq_liab_plus_equity",
                "ok": identity_ok,
                "assets": assets,
                "liabilities_plus_equity": rhs,
                "rel_error": rel,
            }
        )
    else:
        checks.append(
            {
                "id": "assets_eq_liab_plus_equity",
                "ok": False,
                "reason": "missing_components",
            }
        )
        identity_ok = False

    if ca is not None and assets is not None:
        ok = ca <= assets * (1.0 + tolerance)
        checks.append({"id": "current_le_total_assets", "ok": ok, "current": ca, "total": assets})
    if cl is not None and liab is not None:
        ok = cl <= liab * (1.0 + tolerance)
        checks.append(
            {"id": "current_le_total_liabilities", "ok": ok, "current": cl, "total": liab}
        )

    hard_fail = any(
        c["id"] == "assets_eq_liab_plus_equity" and not c.get("ok") for c in checks
    )
    soft_fail = any(not c.get("ok") for c in checks if c["id"] != "assets_eq_liab_plus_equity")

    if hard_fail:
        status = "unverified"
    elif soft_fail:
        status = "verified_with_warnings"
    else:
        status = "verified"

    return {
        "parse_status": status,
        "checks": checks,
        "identity_ok": bool(identity_ok),
    }
