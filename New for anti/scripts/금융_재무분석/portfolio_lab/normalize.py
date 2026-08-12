"""Portfolio input normalization: NAV, credit, residual KRW cash, top-N truncate.

Order (raw dict, before resolve):
  1) Resolve optional net asset value (NAV); ``total_value`` / ``aum_krw`` are legacy aliases
  2) Auto-fill residual as KRW cash only for a cash-funded long-only book
  3) Require an explicit, balanced ledger when the book contains a short or credit debt
  4) Truncate to MAX_NAMES by |value| (largest first); cash keeps if large enough

MAX_NAMES is a product / UI convenience cap (easy to raise to 30 later), not an MPT formula.
"""

from __future__ import annotations

import copy
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# Product cap — raise to 30 when UI allows; keep in one place for Claude UI sync.
MAX_NAMES = 20

_CASH_KRW_QUERIES = frozenset(
    {
        "현금",
        "원화",
        "krw",
        "현금원화",
        "cash:krw",
        "cashkrw",
        "원",
    }
)

_SIZE_BUCKETS: list[tuple[str, float | None, dict[str, Any]]] = [
    # (bucket_id, upper_exclusive_or_None, meta) — lower bound = previous upper
    (
        "micro",
        5e6,
        {
            "label_ko": "소액",
            "label_en": "Micro",
            "names_min": 3,
            "names_max": 8,
            "prefer_etf": True,
            "range_ko": "~500만",
            "range_en": "under ~5M KRW",
        },
    ),
    (
        "small",
        3e7,
        {
            "label_ko": "일반",
            "label_en": "Small",
            "names_min": 5,
            "names_max": 15,
            "prefer_etf": True,
            "range_ko": "500만~3천만",
            "range_en": "~5M–30M KRW",
        },
    ),
    (
        "standard",
        1e8,
        {
            "label_ko": "확대",
            "label_en": "Standard",
            "names_min": 8,
            "names_max": 20,
            "prefer_etf": False,
            "range_ko": "3천만~1억",
            "range_en": "~30M–100M KRW",
        },
    ),
    (
        "large",
        5e8,
        {
            "label_ko": "고액 개인",
            "label_en": "Large retail",
            "names_min": 10,
            "names_max": 30,
            "prefer_etf": False,
            "range_ko": "1억~5억",
            "range_en": "~100M–500M KRW",
        },
    ),
    (
        "overload",
        None,
        {
            "label_ko": "참고 구간 밖",
            "label_en": "Above retail guide",
            "names_min": 10,
            "names_max": 30,
            "prefer_etf": False,
            "range_ko": "5억 초과",
            "range_en": "over ~500M KRW",
        },
    ),
]

FOOTNOTE_KO = "규모 구간 휴리스틱. MPT 종목수 공식 아님."
FOOTNOTE_EN = "Retail size-band heuristic — not an MPT optimal-N formula."


class PortfolioNormalizeError(ValueError):
    """Input total AUM conflict or invalid portfolio numbers."""


def _norm_query(text: str) -> str:
    t = unicodedata.normalize("NFKC", str(text)).strip().lower()
    t = re.sub(r"[\s_\-]+", "", t)
    return t


def is_krw_cash_query(query: str) -> bool:
    return _norm_query(query) in _CASH_KRW_QUERIES


def _read_optional_total(portfolio: dict[str, Any]) -> float | None:
    raw = portfolio.get("net_asset_value")
    if raw is None:
        raw = portfolio.get("nav")
    if raw is None:
        raw = portfolio.get("total_value")
    if raw is None:
        raw = portfolio.get("aum_krw")
    if raw is None or raw == "":
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError) as exc:
        raise PortfolioNormalizeError(f"invalid net_asset_value/nav/total_value/aum_krw: {raw!r}") from exc
    if v <= 0 or not math.isfinite(v):
        return None
    return v


def _read_credit_used(portfolio: dict[str, Any]) -> float:
    """Read an explicit KRW credit/margin debt; never infer it from gross exposure."""
    raw = portfolio.get("credit_used_krw")
    if raw is None:
        raw = portfolio.get("margin_debt_krw")
    if raw is None:
        raw = portfolio.get("credit_debt_krw")
    if raw is None or raw == "":
        return 0.0
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise PortfolioNormalizeError(f"invalid credit_used_krw/margin_debt_krw: {raw!r}") from exc
    if value < 0 or not math.isfinite(value):
        raise PortfolioNormalizeError("credit_used_krw/margin_debt_krw must be a finite non-negative number")
    return value


def size_bucket_for_aum(aum_krw: float) -> dict[str, Any]:
    """Map AUM to retail size guide (100만–5억 product bands)."""
    a = float(aum_krw)
    lower = 0.0
    meta: dict[str, Any] = _SIZE_BUCKETS[-1][2]
    bucket = _SIZE_BUCKETS[-1][0]
    for bid, upper, m in _SIZE_BUCKETS:
        if upper is None or a < upper:
            bucket = bid
            meta = m
            break
        lower = upper
    return {
        "aum_krw": a,
        "bucket": bucket,
        "label_ko": meta["label_ko"],
        "label_en": meta["label_en"],
        "names_min": int(meta["names_min"]),
        "names_max": int(meta["names_max"]),
        "prefer_etf": bool(meta["prefer_etf"]),
        "footnote_ko": FOOTNOTE_KO,
        "footnote_en": FOOTNOTE_EN,
        "range_ko": meta["range_ko"],
        "range_en": meta["range_en"],
        "range_lower_krw": lower if bucket != "micro" else 0.0,
        "range_upper_krw": None if bucket == "overload" else (
            next(u for b, u, _ in _SIZE_BUCKETS if b == bucket)
        ),
    }


def _vs_actual_status(n_names: int, names_min: int, names_max: int) -> str:
    if n_names < names_min:
        return "too_few"
    if n_names > names_max:
        return "too_many"
    return "ok"


def build_size_guide(aum_krw: float | None, n_names: int) -> dict[str, Any] | None:
    if aum_krw is None:
        return None
    guide = size_bucket_for_aum(aum_krw)
    guide["vs_actual"] = {
        "n_names": int(n_names),
        "status": _vs_actual_status(n_names, guide["names_min"], guide["names_max"]),
    }
    return guide


@dataclass
class NormalizeResult:
    portfolio: dict[str, Any]
    aum_krw: float | None = None
    net_asset_value_krw: float | None = None
    gross_exposure_krw: float | None = None
    signed_positions_value_krw: float | None = None
    credit_used_krw: float = 0.0
    total_was_inferred: bool = False
    residual_cash_added: float = 0.0
    truncated_positions: list[dict[str, Any]] = field(default_factory=list)
    positions_truncated_ko: str | None = None
    positions_truncated_en: str | None = None
    size_guide: dict[str, Any] | None = None
    notes_ko: list[str] = field(default_factory=list)
    notes_en: list[str] = field(default_factory=list)
    mode: str = "value"  # value | weight | empty

    def to_meta(self) -> dict[str, Any]:
        return {
            "aum_krw": self.aum_krw,
            "net_asset_value_krw": self.net_asset_value_krw,
            "gross_exposure_krw": self.gross_exposure_krw,
            "signed_positions_value_krw": self.signed_positions_value_krw,
            "credit_used_krw": self.credit_used_krw,
            "total_was_inferred": self.total_was_inferred,
            "residual_cash_added": self.residual_cash_added,
            "max_names": MAX_NAMES,
            "truncated_positions": self.truncated_positions,
            "positions_truncated_ko": self.positions_truncated_ko,
            "positions_truncated_en": self.positions_truncated_en,
            "size_guide": self.size_guide,
            "notes_ko": self.notes_ko,
            "notes_en": self.notes_en,
            "mode": self.mode,
        }


def _signed_value_rows(positions: list[dict[str, Any]]) -> tuple[list[float | None], str]:
    """Return per-row signed notionals (None for weight-only). Detect mixed/pure modes."""
    markers: list[float | None] = []
    has_value = False
    has_weight = False
    for p in positions:
        if not str(p.get("query") or p.get("symbol") or "").strip():
            markers.append(0.0)
            continue
        if "value" in p and p["value"] is not None and p["value"] != "":
            has_value = True
            side = str(p.get("side") or "long").strip().lower()
            val = abs(float(p["value"]))
            markers.append(-val if side in {"short", "sell", "공매도"} else val)
        elif "weight" in p and p["weight"] is not None and p["weight"] != "":
            has_weight = True
            side = str(p.get("side") or "long").strip().lower()
            w = float(p["weight"])
            if side in {"short", "sell", "공매도"} and w > 0:
                w = -w
            markers.append(None)  # weight path tracked separately
            # store signed weight on a private key for truncate ranking
            p["_signed_weight"] = w
        else:
            markers.append(0.0)
    if has_value and has_weight:
        mode = "mixed"
    elif has_value:
        mode = "value"
    elif has_weight:
        mode = "weight"
    else:
        mode = "empty"
    return markers, mode


def _apply_residual_cash(
    positions: list[dict[str, Any]],
    residual: float,
) -> float:
    """Merge residual KRW cash into existing cash line or append query=원화."""
    if residual <= 1e-9:
        return 0.0
    for p in positions:
        q = str(p.get("query") or p.get("symbol") or "")
        if not is_krw_cash_query(q):
            continue
        if "value" in p and p["value"] is not None and p["value"] != "":
            side = str(p.get("side") or "long").strip().lower()
            cur = abs(float(p["value"]))
            if side in {"short", "sell", "공매도"}:
                # unusual; treat residual as long cash on same row magnitude reduction — skip merge
                continue
            p["value"] = cur + residual
            return residual
        p["value"] = residual
        p.pop("weight", None)
        return residual
    positions.append({"query": "원화", "value": residual, "side": "long"})
    return residual


def _truncate_by_abs(
    positions: list[dict[str, Any]],
    *,
    mode: str,
    max_names: int = MAX_NAMES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep top max_names by abs notional / abs weight. All positions ranked (cash included)."""
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for i, p in enumerate(positions):
        q = str(p.get("query") or p.get("symbol") or "").strip()
        if not q:
            continue
        if mode == "weight" or (
            mode == "mixed"
            and not ("value" in p and p["value"] is not None and p["value"] != "")
        ):
            w = p.get("_signed_weight")
            if w is None and "weight" in p and p["weight"] is not None:
                w = float(p["weight"])
            score = abs(float(w or 0.0))
        else:
            if "value" not in p or p["value"] is None or p["value"] == "":
                score = 0.0
            else:
                score = abs(float(p["value"]))
        ranked.append((score, i, p))

    ranked.sort(key=lambda t: (-t[0], t[1]))
    if len(ranked) <= max_names:
        cleaned = []
        for _, _, p in ranked:
            p2 = {k: v for k, v in p.items() if not str(k).startswith("_")}
            cleaned.append(p2)
        return cleaned, []

    keep = ranked[:max_names]
    drop = ranked[max_names:]
    total_gross = sum(s for s, _, _ in ranked) or 1.0
    truncated: list[dict[str, Any]] = []
    for score, _, p in drop:
        name = str(p.get("query") or p.get("symbol") or "")
        val = p.get("value")
        if val is None and "weight" in p:
            val = p.get("weight")
        truncated.append(
            {
                "name": name,
                "query": name,
                "value": float(val) if val is not None and val != "" else score,
                "weight_share": float(score / total_gross),
            }
        )
    cleaned = []
    for _, _, p in keep:
        p2 = {k: v for k, v in p.items() if not str(k).startswith("_")}
        cleaned.append(p2)
    return cleaned, truncated


def _truncation_messages(
    truncated: list[dict[str, Any]],
    *,
    max_names: int,
) -> tuple[str, str]:
    n = len(truncated)
    share = sum(float(t.get("weight_share") or 0.0) for t in truncated)
    names = ", ".join(str(t.get("name") or "?") for t in truncated[:5])
    if n > 5:
        names += " …"
    ko = (
        f"종목이 {max_names + n}개라 평가액(|금액|) 상위 {max_names}개만 분석합니다. "
        f"제외 {n}종 · 합 비중 약 {100.0 * share:.1f}% ({names}). "
        f"제외분은 가짜 ‘기타’ 시계열로 넣지 않습니다."
    )
    en = (
        f"{max_names + n} names entered; analysis keeps the top {max_names} by |value|. "
        f"Dropped {n} line(s) (~{100.0 * share:.1f}% gross: {names}). "
        "Dropped weight is not reassigned to a synthetic ‘other’ series."
    )
    return ko, en


def normalize_portfolio(
    portfolio: dict[str, Any],
    *,
    max_names: int = MAX_NAMES,
) -> NormalizeResult:
    """Normalize a raw portfolio dict before resolve_portfolio.

    Raises PortfolioNormalizeError when declared total is exceeded by entered positions.
    """
    out = copy.deepcopy(portfolio)
    positions = list(out.get("positions") or [])
    # strip blank queries early but keep structure
    positions = [p for p in positions if str(p.get("query") or p.get("symbol") or "").strip()]
    markers, mode = _signed_value_rows(positions)
    result = NormalizeResult(portfolio=out, mode=mode)

    if mode == "empty":
        out["positions"] = positions
        return result

    if mode == "weight":
        # Optional total ignored for residual fill (weights already span 100%).
        cleaned, truncated = _truncate_by_abs(positions, mode="weight", max_names=max_names)
        out["positions"] = cleaned
        result.truncated_positions = truncated
        if truncated:
            ko, en = _truncation_messages(truncated, max_names=max_names)
            result.positions_truncated_ko = ko
            result.positions_truncated_en = en
            result.notes_ko.append(ko)
            result.notes_en.append(en)
        result.size_guide = None
        result.portfolio = out
        return result

    # Value (or mixed: only value rows participate in AUM math)
    value_rows = []
    for p, m in zip(positions, markers):
        if m is None:
            # drop weight-only from AUM path at normalize; resolve would drop mixed anyway
            continue
        value_rows.append(p)

    gross = sum(abs(float(p["value"])) for p in value_rows if p.get("value") is not None)
    signed_positions = sum(float(m or 0.0) for m in markers if m is not None)
    credit_used = _read_credit_used(out)
    has_short = any(float(m or 0.0) < -1e-9 for m in markers if m is not None)
    declared = _read_optional_total(out)
    simple_cash_funded_long_book = not has_short and credit_used <= 1e-9

    if declared is None:
        result.total_was_inferred = True
        aum = float(gross) if simple_cash_funded_long_book else float(signed_positions - credit_used)
    else:
        result.total_was_inferred = False
        aum = float(declared)
        if simple_cash_funded_long_book:
            if gross > aum + 1e-6:
                raise PortfolioNormalizeError(
                    f"position |values| sum ({gross:,.0f}) exceeds net asset value ({aum:,.0f}); "
                    "reduce positions or raise NAV — will not silently drop excess."
                )
            residual = aum - gross
            if residual > 1e-6:
                added = _apply_residual_cash(value_rows, residual)
                result.residual_cash_added = added
                if added > 0:
                    msg_ko = (
                        f"순자산 {aum:,.0f}원 대비 입력 합 {gross:,.0f}원 → "
                        f"잔여 {added:,.0f}원을 원화 현금(cash:krw)으로 자동 배정했습니다."
                    )
                    msg_en = (
                        f"Declared NAV {aum:,.0f} KRW vs entered {gross:,.0f} → "
                        f"residual {added:,.0f} KRW auto-filled as KRW cash."
                    )
                    result.notes_ko.append(msg_ko)
                    result.notes_en.append(msg_en)
        else:
            ledger_nav = signed_positions - credit_used
            if abs(ledger_nav - aum) > max(1e-6, abs(aum) * 1e-8):
                raise PortfolioNormalizeError(
                    "short/credit portfolio ledger does not balance: "
                    f"signed positions ({signed_positions:,.0f}) - credit debt ({credit_used:,.0f}) "
                    f"= {ledger_nav:,.0f}, but declared NAV is {aum:,.0f}. "
                    "Include cash collateral / short-sale proceeds explicitly; residual cash is not auto-filled."
                )

    if aum <= 1e-9:
        raise PortfolioNormalizeError(
            "net asset value must be positive after short positions and credit debt are accounted for"
        )

    # Recompute the submitted ledger after a permitted residual cash fill.
    normalized_signed = sum(
        (-abs(float(p["value"])) if str(p.get("side") or "long").strip().lower() in {"short", "sell", "공매도"}
         else abs(float(p["value"])))
        for p in value_rows
        if p.get("value") is not None
    )
    normalized_gross = sum(abs(float(p["value"])) for p in value_rows if p.get("value") is not None)

    # Book size for size_guide: declared total or full gross after residual cash (before truncate).
    book_aum = float(aum) if aum > 0 else None
    result.aum_krw = book_aum
    result.net_asset_value_krw = book_aum
    result.gross_exposure_krw = normalized_gross
    result.signed_positions_value_krw = normalized_signed
    result.credit_used_krw = credit_used

    cleaned, truncated = _truncate_by_abs(value_rows, mode="value", max_names=max_names)
    out["positions"] = cleaned
    result.truncated_positions = truncated
    if truncated:
        ko, en = _truncation_messages(truncated, max_names=max_names)
        result.positions_truncated_ko = ko
        result.positions_truncated_en = en
        result.notes_ko.append(ko)
        result.notes_en.append(en)

    result.size_guide = build_size_guide(result.aum_krw, n_names=len(cleaned))
    result.portfolio = out
    return result
