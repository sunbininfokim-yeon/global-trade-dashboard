"""Refresh the 정책 › 미국 › 예산 monthly actuals from Treasury MTS Table 1.

Writes public/data/us_budget/mts_live_v1.json only. The reviewed annual
snapshot (annual_v1.json, OMB + MTS vintages pinned by sources.json) is never
touched here: OMB publishes once a year and its tables need a reviewed
regeneration, so this script only *reports* a new OMB vintage.

Rules carried over from the Codex handoff (docs/prototypes/us-budget/README.md):
- A Table 1 report holds a "FY yyyy" parent block per fiscal year; months are
  its children with record_type_cd == "MTH". record_date is the report date,
  not the observed month. Year-to-Date rows are never added to monthly rows.
- Only observed months are stored. No FY proposal is spread across months.
- On any fetch/parse/validation failure the existing file is kept as is and
  the script exits non-zero, so the workflow shows the failure and commits
  nothing. A failure is never written as a fresh, successful refresh.

Usage:
  python refresh_mts.py                 # update mts_live_v1.json if MTS moved on
  python refresh_mts.py --dry-run       # fetch and validate, write nothing
  python refresh_mts.py --verify-snapshot
      # re-derive the reviewed 2026-09-30 months from the live API and require
      # an exact match with annual_v1.json (proves the parsing on real data)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_1"
OMB_URL = "https://www.whitehouse.gov/wp-content/uploads/{year}/04/hist01z1_fy{fy}.xlsx"
UA = "Mozilla/5.0 (compatible; chokemonitor-us-budget/1.0; research)"
DATA_DIR = Path(__file__).resolve().parents[2] / "public" / "data" / "us_budget"
LIVE = DATA_DIR / "mts_live_v1.json"
ANNUAL = DATA_DIR / "annual_v1.json"
WINDOW = 36
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
RECEIPTS, OUTLAYS, DEFICIT = "current_month_gross_rcpt_amt", "current_month_gross_outly_amt", "current_month_dfct_sur_amt"


class RefreshError(RuntimeError):
    pass


def http_json(url: str, timeout: int = 45) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:  # 403/429/5xx: keep the published file
        raise RefreshError(f"MTS HTTP {err.code} for {url}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise RefreshError(f"MTS unreachable: {err}") from err


def latest_record_date(get: Callable[[str], dict] = http_json) -> str:
    q = urllib.parse.urlencode({"sort": "-record_date", "page[size]": "1", "fields": "record_date"})
    rows = get(f"{BASE}?{q}").get("data") or []
    if not rows or not rows[0].get("record_date"):
        raise RefreshError("MTS Table 1 returned no record_date")
    return rows[0]["record_date"]


def report_rows(record_date: str, get: Callable[[str], dict] = http_json) -> List[dict]:
    q = urllib.parse.urlencode({"filter": f"record_date:eq:{record_date}", "page[size]": "1000"})
    rows = get(f"{BASE}?{q}").get("data") or []
    if not rows:
        raise RefreshError(f"MTS Table 1 has no rows for {record_date}")
    return rows


def amount(row: dict, field: str) -> float:
    if field not in row:
        raise RefreshError(f"MTS Table 1 field {field!r} missing; row keys: {sorted(row)}")
    raw = row[field]
    if raw in (None, "", "null"):
        raise RefreshError(f"MTS Table 1 {field} empty for {row.get('classification_desc')!r}")
    value = float(raw)
    if not math.isfinite(value):
        raise RefreshError(f"MTS Table 1 {field} not finite")
    return value


def parse_report(rows: List[dict], record_date: str) -> Dict[str, object]:
    """Monthly rows per fiscal-year block, plus that report's fiscal year to date."""
    blocks = {}
    for r in rows:
        desc = (r.get("classification_desc") or "").strip()
        if desc.upper().startswith("FY ") and desc[3:].strip().isdigit():
            blocks[r.get("classification_id")] = int(desc[3:].strip())
    if not blocks:
        raise RefreshError("MTS Table 1 has no 'FY yyyy' parent blocks")
    months: Dict[str, dict] = {}
    ytd: Dict[int, dict] = {}
    for r in rows:
        fy = blocks.get(r.get("parent_id"))
        if fy is None:
            continue
        desc = (r.get("classification_desc") or "").strip()
        if r.get("record_type_cd") == "MTH" and desc in MONTHS:
            m = MONTHS[desc]
            year = fy - 1 if m >= 10 else fy  # October opens the fiscal year
            key = f"{year:04d}-{m:02d}"
            if key in months:
                raise RefreshError(f"MTS Table 1 repeats month {key}")
            rec, out, dfc = amount(r, RECEIPTS), amount(r, OUTLAYS), amount(r, DEFICIT)
            months[key] = {"month": key, "receipts": rec, "outlays": out, "deficit": out - rec, "vintage": record_date,
                           "_reported_deficit": dfc}
        elif desc.lower().startswith("year-to-date"):
            ytd[fy] = {"receipts": amount(r, RECEIPTS), "outlays": amount(r, OUTLAYS)}
    if not months:
        raise RefreshError("MTS Table 1 has no monthly (MTH) rows under the FY blocks")
    for row in months.values():
        reported = row.pop("_reported_deficit")
        # Table 1 signs deficits negative (surplus positive). Accept either
        # sign convention but require the identity outlays - receipts.
        if abs(abs(reported) - abs(row["deficit"])) > 1.0:
            raise RefreshError(f"MTS {row['month']}: deficit {reported} does not match outlays - receipts")
    return {"months": months, "ytd": ytd}


def check_sequence(months: List[dict]) -> None:
    keys = [m["month"] for m in months]
    for a, b in zip(keys, keys[1:]):
        ya, ma = map(int, a.split("-"))
        yb, mb = map(int, b.split("-"))
        if (yb * 12 + mb) - (ya * 12 + ma) != 1:
            raise RefreshError(f"monthly series has a gap or overlap between {a} and {b}")
    for m in months:
        if abs(m["outlays"] - m["receipts"] - m["deficit"]) > 1.0:
            raise RefreshError(f"{m['month']}: deficit identity broken")


def merge(existing: dict, parsed: Dict[str, object], record_date: str) -> dict:
    by_month = {m["month"]: m for m in existing["months"]}
    new_months = parsed["months"]
    # Overlapping months from the previous report must agree closely; a large
    # jump means the parse picked the wrong rows, not a Treasury revision.
    for key, row in new_months.items():
        old = by_month.get(key)
        if old and old["outlays"] and abs(row["outlays"] / old["outlays"] - 1) > 0.02:
            raise RefreshError(f"{key}: outlays moved >2% vs the published value ({old['outlays']} -> {row['outlays']})")
        by_month[key] = row
    months = sorted(by_month.values(), key=lambda m: m["month"])[-WINDOW:]
    if len(months) < WINDOW:
        raise RefreshError(f"only {len(months)} months after merge; expected {WINDOW}")
    check_sequence(months)
    latest = months[-1]["month"]
    ly, lm = map(int, latest.split("-"))
    fy = ly + 1 if lm >= 10 else ly
    ytd = parsed["ytd"].get(fy)
    fytd = None
    if ytd:
        fytd = {"fy": fy, "through": latest, "receipts": ytd["receipts"], "outlays": ytd["outlays"],
                "deficit": ytd["outlays"] - ytd["receipts"], "complete": lm == 9}
    out = dict(existing)
    out.update({"mts_record_date": record_date, "months": months, "fytd": fytd})
    out["note"] = "Treasury MTS Table 1 monthly actuals; updated by scripts/us_budget/refresh_mts.py."
    return out


def omb_watch(annual: dict, head: Optional[Callable[[str], int]] = None) -> Optional[dict]:
    """Report (never import) an OMB budget newer than the snapshot's proposal year."""
    proposal_fy = int(annual["fy2027"]["year"]["fy"]) if "fy2027" in annual else None
    if not proposal_fy:
        return None
    nxt = proposal_fy + 1
    url = OMB_URL.format(year=nxt - 1, fy=nxt)
    def _head(u: str) -> int:
        req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status
        except urllib.error.HTTPError as err:
            return err.code
        except (urllib.error.URLError, TimeoutError):
            return 0
    status = (head or _head)(url)
    return {"next_fy": nxt, "url": url, "available": status == 200}


def verify_snapshot(get: Callable[[str], dict] = http_json) -> int:
    annual = json.loads(ANNUAL.read_text(encoding="utf-8"))
    reviewed = {m["month"]: m for m in annual["budget"]["monthly"] if m["vintage"] == "2026-09-30"}
    parsed = parse_report(report_rows("2026-09-30", get), "2026-09-30")["months"]
    bad = []
    for key, want in reviewed.items():
        got = parsed.get(key)
        if not got:
            bad.append(f"{key}: missing from live parse")
            continue
        for f in ("receipts", "outlays", "deficit"):
            if abs(got[f] - want[f]) > 1.0:
                bad.append(f"{key} {f}: live {got[f]} vs snapshot {want[f]}")
    if bad:
        print("snapshot verification FAILED:\n  " + "\n  ".join(bad[:20]), file=sys.stderr)
        return 1
    print(f"snapshot verification OK: {len(reviewed)} months of the 2026-09-30 report match exactly")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify-snapshot", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.verify_snapshot:
            return verify_snapshot()
        existing = json.loads(LIVE.read_text(encoding="utf-8"))
        annual = json.loads(ANNUAL.read_text(encoding="utf-8"))
        watch = omb_watch(annual)
        if watch and watch["available"]:
            print(f"::warning::OMB FY{watch['next_fy']} budget tables are published ({watch['url']}); "
                  "the annual snapshot needs a reviewed regeneration")
        record_date = latest_record_date()
        print(f"MTS latest report: {record_date} (published file: {existing['mts_record_date']})")
        if record_date <= existing["mts_record_date"]:
            changed_watch = watch != existing.get("omb_watch") and watch is not None
            if changed_watch and not args.dry_run:
                existing["omb_watch"] = watch
                LIVE.write_text(json.dumps(existing, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                print("OMB watch status updated")
            else:
                print("no newer MTS report; nothing to write")
            return 0
        merged = merge(existing, parse_report(report_rows(record_date), record_date), record_date)
        merged["omb_watch"] = watch
        print(f"months {merged['months'][0]['month']}..{merged['months'][-1]['month']}; fytd {merged['fytd']}")
        if args.dry_run:
            print("dry run: not writing")
            return 0
        LIVE.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {LIVE}")
        return 0
    except RefreshError as err:
        print(f"::error::US budget refresh failed, published file kept: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
