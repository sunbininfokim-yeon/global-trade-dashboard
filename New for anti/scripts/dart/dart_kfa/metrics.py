"""L2 — declarative metric engine (pure functions, null on missing)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_metrics_spec(path: Path | None = None) -> dict[str, Any]:
    p = path or (CONFIG_DIR / "metrics.spec.json")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _is_number_token(token: Any) -> bool:
    if isinstance(token, (int, float)) and not isinstance(token, bool):
        return True
    if isinstance(token, str):
        try:
            float(token)
            return True
        except ValueError:
            return False
    return False


def _as_number(token: Any) -> float:
    return float(token)


def eval_expr(
    expr: Any,
    env: dict[str, float | None],
) -> tuple[float | None, str | None]:
    """Evaluate a polish-ish nested formula list or account key / literal.

    Supported forms:
      "ACCOUNT"
      "1.5"
      ["A", "/", "B"]
      ["A", "-", "B"]
      ["A", "+", "B"]
      ["A", "*", "B"]
      [["A", "-", "B"], "/", "C"]
    """
    if isinstance(expr, list):
        if len(expr) == 2 and expr[0] == "abs":
            v, reason = eval_expr(expr[1], env)
            if v is None:
                return None, reason
            return abs(v), None
        if len(expr) == 1:
            return eval_expr(expr[0], env)
        if len(expr) == 3:
            left, op, right = expr
            lv, lreason = eval_expr(left, env)
            if lv is None:
                return None, lreason
            rv, rreason = eval_expr(right, env)
            if rv is None:
                return None, rreason
            if op == "+":
                return lv + rv, None
            if op == "-":
                return lv - rv, None
            if op == "*":
                return lv * rv, None
            if op == "/":
                if rv == 0:
                    return None, "div_by_zero"
                return lv / rv, None
            return None, f"unknown_op:{op}"
        return None, "bad_formula_arity"

    if _is_number_token(expr):
        return _as_number(expr), None

    if isinstance(expr, str):
        if expr not in env:
            return None, f"missing:{expr}"
        val = env[expr]
        if val is None:
            return None, f"missing:{expr}"
        return float(val), None

    return None, "bad_token"


def _build_env(
    amounts: dict[str, float | None],
    derived_spec: dict[str, Any] | None,
) -> tuple[dict[str, float | None], dict[str, str]]:
    env: dict[str, float | None] = dict(amounts)
    reasons: dict[str, str] = {}
    if not derived_spec:
        return env, reasons
    # derived may depend on other derived — resolve in declaration order
    for name, formula in derived_spec.items():
        val, reason = eval_expr(formula, env)
        env[name] = val
        if reason:
            reasons[name] = reason
    return env, reasons


def compute_metrics(
    amounts: dict[str, float | None],
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mspec = spec or load_metrics_spec()
    metrics_def: dict[str, Any] = mspec.get("metrics") or {}
    out: dict[str, Any] = {}

    for mid, meta in metrics_def.items():
        requires = meta.get("requires") or []
        missing = [r for r in requires if amounts.get(r) is None]
        if missing:
            out[mid] = {
                "value": None,
                "unit": meta.get("unit"),
                "label": meta.get("label"),
                "reason": "missing:" + ",".join(missing),
            }
            continue

        env, derived_reasons = _build_env(amounts, meta.get("derived"))
        if any(k in derived_reasons for k in (meta.get("derived") or {})):
            # if any derived failed, try still evaluating; surface first reason
            pass

        raw, reason = eval_expr(meta["formula"], env)
        if raw is None:
            out[mid] = {
                "value": None,
                "unit": meta.get("unit"),
                "label": meta.get("label"),
                "reason": reason or derived_reasons.get(next(iter(derived_reasons), ""), "error"),
            }
            continue

        scale = float(meta.get("scale") or 1)
        value = raw * scale
        out[mid] = {
            "value": round(value, 4) if meta.get("unit") != "currency" else round(value, 2),
            "unit": meta.get("unit"),
            "label": meta.get("label"),
            "polarity": meta.get("polarity"),
            "reason": None,
        }
    return out


def trend_3y(
    amounts_series: list[dict[str, float | None]],
    metric_id: str,
    spec: dict[str, Any] | None = None,
) -> list[float | None]:
    """Compute one metric across [prior2, prior, current] amount dicts."""
    return [compute_metrics(a, spec).get(metric_id, {}).get("value") for a in amounts_series]
