#!/usr/bin/env python3
"""Keyless Treasury MTS feed. Publish one validated JSON with atomic replacement.

OMB proposals remain in a separate snapshot; this collector never edits them.
Uses Python's standard library. No Supabase or LLM credentials are read.
"""
import argparse
import calendar
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.parse
import urllib.request

BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts"
MONTHS = {name: i for i, name in enumerate(calendar.month_name) if name}
MONEY = ("current_month_gross_rcpt_amt", "current_month_gross_outly_amt", "current_month_dfct_sur_amt")
NULLS = (None, "", "null")


def amount(value):
    if value in NULLS:
        raise ValueError("Missing monetary observation")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid monetary observation") from exc
    if not result.is_finite():
        raise ValueError("Non-finite monetary observation")
    return result


def equal(a, b):
    if abs(a - b) > Decimal("0.05"):
        raise ValueError(f"Budget reconciliation failed: {a} != {b}")


def unique(rows, **criteria):
    matches = [r for r in rows if all(r.get(k) == v for k, v in criteria.items())]
    if len(matches) != 1:
        raise ValueError(f"Expected one source row for {criteria}; found {len(matches)}")
    return matches[0]


def monthly_rows(rows, vintage):
    """Resolve observation month from its own FY parent, never record_date."""
    date.fromisoformat(vintage)
    parents = {r["classification_id"]: r for r in rows}
    output = {}
    for r in rows:
        if r.get("record_type_cd") != "MTH":
            continue
        parent = parents.get(r.get("parent_id"), {})
        label = parent.get("classification_desc", "").split()
        if len(label) != 2 or label[0] != "FY" or not label[1].isdigit():
            raise ValueError("MTH row has no unambiguous fiscal-year parent")
        fy = int(label[1])
        month = MONTHS.get(r.get("classification_desc"))
        if month is None:
            raise ValueError("Unknown MTS month label")
        key = f"{fy - (month >= 10):04d}-{month:02d}"
        if all(r.get(k) in NULLS for k in MONEY) and key > vintage[:7]:
            continue  # Future months printed as blank in a current-FY table.
        if key > vintage[:7]:
            raise ValueError("Future actual observation")
        receipts, outlays, deficit = (amount(r.get(k)) for k in MONEY)
        equal(outlays - receipts, deficit)
        if key in output:
            raise ValueError(f"Duplicate month within a publication: {key}")
        output[key] = dict(month=key, fy=fy, receipts=receipts, outlays=outlays,
                           deficit=deficit, vintage=vintage, status="actual")
    return output


def month_shift(month, delta):
    year, m = map(int, month.split("-"))
    year, m = divmod(year * 12 + m - 1 + delta, 12)
    return f"{year:04d}-{m + 1:02d}"


def rolling_months(publications, latest):
    observations = {}
    for vintage, rows in sorted(publications.items()):
        observations.update(monthly_rows(rows, vintage))  # Most recent revision wins.
    expected = [month_shift(latest[:7], i) for i in range(-35, 1)]
    if any(m not in observations for m in expected):
        raise ValueError("Incomplete rolling 36-month actual coverage")
    return [observations[m] for m in expected]


def detail_groups(rows, root_name, total_name):
    root = unique(rows, classification_desc=root_name, sequence_level_nbr="1")
    total = unique(rows, parent_id=root["classification_id"], classification_desc=total_name)
    children = {}
    for r in rows:
        children.setdefault(r.get("parent_id"), []).append(r)

    def value(r, field, ancestors=()):
        key = r["classification_id"]
        if key in ancestors:
            raise ValueError("Cyclic MTS classification hierarchy")
        if r.get(field) not in NULLS:
            return amount(r[field])
        sub = [c for c in children.get(key, []) if c.get("data_type_cd") != "T"]
        if not sub:
            return None  # e.g. Allowances has a budget estimate but no actual.
        values = [value(c, field, (*ancestors, key)) for c in sub]
        if any(v is None for v in values):
            raise ValueError("Incomplete classification subtotal")
        return sum(values, Decimal(0))

    result = []
    for r in children.get(root["classification_id"], []):
        if r.get("data_type_cd") == "T":
            continue
        current = value(r, "current_fytd_rcpt_outly_amt")
        prior = value(r, "prior_fytd_rcpt_outly_amt")
        result.append(dict(id=r["line_code_nbr"], name=r["classification_desc"],
                           value=current, prior=prior, status="actual" if current is not None else "missing"))
    total_amount = amount(total.get("current_fytd_rcpt_outly_amt"))
    equal(sum((r["value"] for r in result if r["value"] is not None), Decimal(0)), total_amount)
    prior_total = amount(total.get("prior_fytd_rcpt_outly_amt"))
    equal(sum((r["prior"] for r in result if r["prior"] is not None), Decimal(0)), prior_total)
    return result, total_amount


def build(publications, table3, table6, latest, sources):
    for rows in [*publications.values(), table3, table6]:
        if not rows:
            raise ValueError("Empty MTS publication")
    for vintage, rows in [*publications.items(), (latest, table3), (latest, table6)]:
        if any(r.get("record_date") != vintage for r in rows):
            raise ValueError("Mixed publication dates")
        ids = [r["classification_id"] for r in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate source classification IDs")
    monthly = rolling_months(publications, latest)
    fy = int(latest[:4]) + (int(latest[5:7]) >= 10)
    parent = unique(publications[latest], classification_desc=f"FY {fy}", sequence_level_nbr="1")
    ytd = unique(publications[latest], parent_id=parent["classification_id"], classification_desc="Year-to-Date")
    receipts, outlays, deficit = (amount(ytd.get(k)) for k in MONEY)
    equal(outlays - receipts, deficit)
    fy_months = [r for r in monthly if r["fy"] == fy]
    expected_count = (int(latest[5:7]) - 10) % 12 + 1
    if len(fy_months) != expected_count:
        raise ValueError("Incomplete current fiscal-year coverage")
    for field, total in zip(("receipts", "outlays", "deficit"), (receipts, outlays, deficit)):
        equal(sum((r[field] for r in fy_months), Decimal(0)), total)
    receipt_groups, receipt_total = detail_groups(table3, "Budget Receipts", "Total Receipts")
    agencies, outlay_total = detail_groups(table3, "Budget Outlays", "Total Outlays")
    equal(receipts, receipt_total)
    equal(outlays, outlay_total)
    borrowing = amount(unique(table6, classification_desc="Total Borrowing from the Public")["fytd_net_txn_amt"])
    cash = amount(unique(table6, classification_desc="Federal Reserve Account")["fytd_net_txn_amt"])
    financing_total = amount(unique(table6, classification_desc="Total Budget and Off-Budget Federal Entities (Financing of Deficit (+) or Disposition of Surplus (-))")["fytd_net_txn_amt"])
    equal(deficit, financing_total)
    return dict(schema_version=1, unit="USD", status="actual", publication_date=latest,
                coverage=dict(start=monthly[0]["month"], end=monthly[-1]["month"], months=36),
                monthly=monthly,
                fiscal_ytd=dict(fy=fy, through=latest[:7], complete_fy=latest[5:] == "09-30",
                                receipts=receipts, outlays=outlays, deficit=deficit,
                                receipts_by_category=receipt_groups, agencies=agencies,
                                finance=dict(borrowing=borrowing, cashIncrease=cash,
                                             other=deficit - borrowing + cash, deficit=deficit)),
                definitions=dict(prior="Same publication, prior FY through equivalent month; not full prior year unless September.",
                                 borrowing="Net borrowing from the public, not gross issuance or tax revenue.",
                                 other="Residual financing and adjustments; not a single official account.",
                                 agencies="Net agency outlays; negative values retained. Not a mandatory/discretionary split."),
                sources=sources)


def request(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ChokeMonitor-USBudget/1.0", "Accept": "application/json"})
    # Do not hammer a source after 403/429; any HTTP/network error aborts this run.
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def fetch_table(table, vintage, sources, getter=request):
    rows = []
    for page in range(1, 21):
        params = {"filter": f"record_date:eq:{vintage}", "page[size]": "1000", "page[number]": str(page), "sort": "record_date,print_order_nbr"}
        url = f"{BASE}/mts_table_{table}?{urllib.parse.urlencode(params)}"
        raw = getter(url)
        payload = json.loads(raw)
        batch = payload["data"]
        pages = int(payload["meta"]["total-pages"])
        if not batch or pages < page:
            raise ValueError("Empty or inconsistent API page")
        rows.extend(batch)
        sources.append(dict(table=table, publication_date=vintage, url=url,
                            response_sha256=hashlib.sha256(raw).hexdigest()))
        if page == pages:
            if len(rows) != int(payload["meta"]["total-count"]):
                raise ValueError("Truncated API response")
            return rows
    raise ValueError("MTS pagination exceeds safety limit")


def collect(getter=request):
    url = f"{BASE}/mts_table_1?sort=-record_date&page%5Bsize%5D=1"
    latest = json.loads(getter(url))["data"][0]["record_date"]
    stamp = date.fromisoformat(latest)
    if stamp.day != calendar.monthrange(stamp.year, stamp.month)[1]:
        raise ValueError("Latest publication is not a month end")
    sources = []
    publications = {latest: fetch_table(1, latest, sources, getter)}
    # September anchors backfill older months. Stop when exact coverage is reached.
    end_year = stamp.year if stamp.month >= 9 else stamp.year - 1
    for year in range(end_year, end_year - 4, -1):
        try:
            rolling_months(publications, latest)
            break
        except ValueError as exc:
            if str(exc) != "Incomplete rolling 36-month actual coverage":
                raise
        anchor = f"{year}-09-30"
        if anchor not in publications:
            publications[anchor] = fetch_table(1, anchor, sources, getter)
    table3 = fetch_table(3, latest, sources, getter)
    table6 = fetch_table(6, latest, sources, getter)
    result = build(publications, table3, table6, latest, sources)
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    return result


def publish(result, output):
    """Never truncate the previous good file on fetch/parse/validation failure."""
    data = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False,
                      default=lambda n: float(n) if isinstance(n, Decimal) else str(n)) + "\n"
    output = Path(output)
    if output.exists():
        previous = json.loads(output.read_text())
        if previous.get("publication_date", "") > result["publication_date"]:
            raise ValueError("Refusing to replace newer publication with older data")
    output.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as handle:
            name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, output)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect()
    publish(result, args.output)
    print(f"MTS {result['publication_date']}: 36 months, {len(result['fiscal_ytd']['agencies'])} agency groups; validated and saved.")


if __name__ == "__main__":
    main()
