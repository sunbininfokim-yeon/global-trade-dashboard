"""Free credit-market panel: only sources we can keep stable without paid feeds.

Included (US SEC, free):
  - Interest coverage / effective interest rate (from statements → ma_metrics)
  - Debt-related filing index (424B*, FWP, 8-K items 1.01 / 2.03)
  - High-confidence coupon / principal parse from 424B primary HTML (optional)

Omitted by design (not free+stable for single-name):
  - Agency credit ratings as a time series
  - Single-name corporate CDS
  - News-site scrape of either
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from .sec_fetch import CACHE_DIR, DEFAULT_UA, SecApiError, fetch_submissions

# Forms that are prospectus / free-writing for registered notes.
PROSPECTUS_FORMS = frozenset(
    {
        "424B1",
        "424B2",
        "424B3",
        "424B4",
        "424B5",
        "424B7",
        "424B8",
        "FWP",
    }
)
# 8-K items commonly used for debt creation / entry into a debt agreement.
DEBT_8K_ITEMS = ("1.01", "2.03")

# Loose but gated parsers — values are dropped unless they look like bond terms.
_RE_COUPON = re.compile(
    r"(?:^|[^\d])(\d{1,2}(?:\.\d{1,3})?)\s*%\s*"
    r"(?:Senior\s+)?(?:Notes?|Debentures?|Bonds?)\b",
    re.I,
)
_RE_RATE = re.compile(
    r"(?:interest\s+rate|coupon(?:\s+rate)?|bear(?:ing)?\s+interest(?:\s+at)?)"
    r"\s*(?:of\s*|at\s*)?(\d{1,2}(?:\.\d{1,3})?)\s*%",
    re.I,
)
_RE_PRINCIPAL = re.compile(
    r"(?:"
    r"(?:aggregate\s+)?principal\s+amount\s+of\s+\$\s*([\d,]+(?:\.\d+)?)"
    r"|"
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:aggregate\s+)?principal\s+amount"
    r")"
    r"(?:\s*(million|billion))?",
    re.I,
)
_RE_MATURITY = re.compile(
    r"(?:matur(?:ity|ing)|due)\s*(?:date\s*)?(?:on\s*|of\s*)?"
    r"((?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4})",
    re.I,
)


def _cell(value: float | None, *, unit: str, label: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "value": None if value is None else round(value, 4),
        "unit": unit,
        "label": label,
        "reason": reason,
    }


def _archive_url(cik_int: int, accession: str, primary: str) -> str:
    acc = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik_int)}/{acc}/"
        f"{quote(primary)}"
    )


def classify_debt_filing(form: str, items: str | None) -> str | None:
    f = (form or "").upper()
    it = items or ""
    if f in PROSPECTUS_FORMS or f.startswith("424"):
        return "prospectus_or_fwp"
    if f in ("8-K", "8-K/A") and any(x in it for x in DEBT_8K_ITEMS):
        return "eight_k_debt_item"
    if f.startswith("S-3"):
        return "shelf_registration"
    return None


def list_debt_filings(
    submissions: dict[str, Any],
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Index debt-related filings from SEC submissions JSON (no document fetch)."""
    cik_int = int(submissions.get("cik") or 0)
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    primaries = recent.get("primaryDocument") or []
    items_col = recent.get("items") or []

    out: list[dict[str, Any]] = []
    n = min(len(forms), len(dates), len(accessions), len(primaries))
    for i in range(n):
        form = forms[i]
        items = items_col[i] if i < len(items_col) else ""
        kind = classify_debt_filing(form, items)
        if kind is None:
            continue
        acc = accessions[i]
        prim = primaries[i]
        out.append(
            {
                "form": form,
                "filed": dates[i],
                "items": items or None,
                "accession": acc,
                "primary_document": prim,
                "kind": kind,
                "url": _archive_url(cik_int, acc, prim) if cik_int and prim else None,
            }
        )
        if len(out) >= limit:
            break
    return out


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_money(num: str, scale: str | None) -> float:
    v = float(num.replace(",", ""))
    s = (scale or "").lower()
    if s == "million":
        return v * 1_000_000.0
    if s == "billion":
        return v * 1_000_000_000.0
    return v


def parse_offering_terms(text: str) -> dict[str, Any] | None:
    """Strict-ish parse. Returns None if nothing high-confidence is found."""
    if not text or len(text) < 80:
        return None
    window = text[:120_000]

    coupons: list[float] = []
    for rx in (_RE_COUPON, _RE_RATE):
        for m in rx.findall(window):
            try:
                c = float(m)
            except (TypeError, ValueError):
                continue
            if 0.05 <= c <= 20.0:  # sane coupon band for corporates
                coupons.append(c)

    principals: list[float] = []
    for m in _RE_PRINCIPAL.finditer(window):
        num = m.group(1) or m.group(2)
        scale = m.group(3)
        if num:
            principals.append(_parse_money(num, scale))

    mats = [m.group(1) for m in _RE_MATURITY.finditer(window)]

    # Require at least a coupon OR (principal + maturity) to avoid junk snippets.
    if not coupons and not (principals and mats):
        return None

    # Prefer the first few distinct coupons (multi-tranche common).
    uniq_c: list[float] = []
    for c in coupons:
        if c not in uniq_c:
            uniq_c.append(c)
        if len(uniq_c) >= 6:
            break

    return {
        "coupons_pct": uniq_c or None,
        "principal_usd": principals[:6] or None,
        "maturity_dates_text": mats[:6] or None,
        "confidence": "high" if uniq_c and principals else "medium",
        "parser": "sec_424_html_regex_v1",
    }


def _http_get_text(url: str, *, timeout: float = 45.0) -> str:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={"User-Agent": DEFAULT_UA, "Accept": "text/html,application/xhtml+xml"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise SecApiError(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise SecApiError(f"network error: {e}") from e


def enrich_filings_with_terms(
    filings: list[dict[str, Any]],
    *,
    max_docs: int = 3,
) -> list[dict[str, Any]]:
    """Fetch a few prospectus pages and attach parsed terms when confidence ok."""
    done = 0
    out: list[dict[str, Any]] = []
    for f in filings:
        row = dict(f)
        if (
            done < max_docs
            and row.get("kind") == "prospectus_or_fwp"
            and row.get("url")
        ):
            try:
                html = _http_get_text(row["url"])
                terms = parse_offering_terms(_strip_html(html))
                if terms:
                    row["terms"] = terms
                done += 1
            except SecApiError as e:
                row["terms_error"] = str(e)
        out.append(row)
    return out


def build_credit_panel(
    *,
    ma: dict[str, Any] | None = None,
    amounts: dict[str, float | None] | None = None,
    debt_filings: list[dict[str, Any]] | None = None,
    source: str = "sec",
) -> dict[str, Any]:
    """Assemble credit block attached to dart-company JSON."""
    ma = ma or {}
    amounts = amounts or {}

    def ma_cell(key: str) -> dict[str, Any]:
        cell = ma.get(key)
        return cell if isinstance(cell, dict) else _cell(None, unit="x", label=key, reason="missing")

    interest = amounts.get("INTEREST_EXPENSE")
    panel = {
        "schema": "kfa-credit-v1",
        "source": source,
        "coverage": {
            "interest_coverage": ma_cell("interest_coverage"),
            "interest_burden": ma_cell("interest_burden"),
            "effective_interest_rate_pct": ma_cell("effective_interest_rate_pct"),
            "interest_expense": _cell(
                float(interest) if interest is not None else None,
                unit="currency",
                label="이자비용",
                reason=None if interest is not None else "missing:INTEREST_EXPENSE",
            ),
        },
        "debt_stock": {
            "gross_interest_bearing_debt": ma_cell("gross_interest_bearing_debt"),
            "net_debt": ma_cell("net_debt"),
            "net_debt_to_ebitda": ma_cell("net_debt_to_ebitda"),
        },
        "debt_filings": {
            "available": bool(debt_filings),
            "count": len(debt_filings or []),
            "items": debt_filings or [],
            "note_ko": (
                "SEC 제출 목록에서 회사채 관련 양식(424B·FWP·8-K 1.01/2.03·S-3)만 골랐습니다. "
                "쿠폰·규모는 일부 프로스펙트에서 정규식으로만 채우며, 없으면 null 입니다."
            ),
        },
        "ratings": {
            "status": "omitted",
            "reason": "no_free_stable_single_name_rating_feed",
            "reason_ko": (
                "S&P/Moody’s/Fitch 단일 발행체 등급 시계열은 무료·안정 API가 없어 제외. "
                "공시 본문에 뜨는 등급은 정규식 오탐이 많아 넣지 않음."
            ),
        },
        "cds": {
            "status": "omitted",
            "reason": "no_free_stable_single_name_cds",
            "reason_ko": (
                "단일 기업 CDS는 Markit/유료 피드를 전제로 함. "
                "뉴스·블로그 스크랩은 불안정해 제외. 매크로의 국채 CDS와 혼동 금지."
            ),
        },
        "notes_ko": [
            "무료·안정 = SEC companyfacts + submissions (+ 선택적 424 HTML 파싱).",
            "유효이자율 대용은 회계 평균 비용이며 TRACE YTM·신규 발행 쿠폰과 다름.",
            "신용등급·기업 CDS는 안정 무료 소스가 확인될 때까지 필드 자체를 비움(omitted).",
        ],
    }
    return panel


def credit_panel_for_cik(
    cik: str,
    *,
    ma: dict[str, Any] | None = None,
    amounts: dict[str, float | None] | None = None,
    use_cache: bool = True,
    parse_docs: bool = True,
    max_docs: int = 3,
    limit: int = 25,
) -> dict[str, Any]:
    """Live SEC path used by fetch_live."""
    subs = fetch_submissions(cik, use_cache=use_cache)
    filings = list_debt_filings(subs, limit=limit)
    if parse_docs and filings:
        filings = enrich_filings_with_terms(filings, max_docs=max_docs)
    return build_credit_panel(
        ma=ma,
        amounts=amounts,
        debt_filings=filings,
        source="sec_submissions+statements",
    )


# silence unused import warning for CACHE_DIR if linters care — used by tests/cache layout
_ = CACHE_DIR
