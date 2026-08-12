"""Extract GBR Commons + ISR Knesset composition and refresh governance polls (document/API extract)."""

from __future__ import annotations

import json
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
OUT = ROOT / "config" / "extracted"
OUT.mkdir(parents=True, exist_ok=True)
UA = "election-watch/1.0 (+global-trade-dashboard research)"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch(url: str, dest: Path, timeout: float = 45.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Prefer curl when available (sandbox/proxy friendlier than urllib in this env).
    import shutil
    import subprocess

    curl = shutil.which("curl")
    if curl:
        r = subprocess.run(
            [curl, "-sL", "--max-time", str(int(timeout)), "-A", UA, "-o", str(dest), url],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dest.write_bytes(resp.read())
    return dest


def strip_tags(html: str) -> str:
    t = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<style[^>]*>.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def extract_gbr_commons(*, date: str = "2026-08-08", refresh: bool = True) -> Dict[str, Any]:
    raw_dir = RAW / "gbr"
    api_path = raw_dir / "state_of_parties.json"
    burnham_path = raw_dir / "govuk_burnham.html"
    url = f"https://members-api.parliament.uk/api/Parties/StateOfTheParties/1/{date}"
    if refresh or not api_path.exists() or api_path.stat().st_size < 50:
        fetch(url, api_path)
    if refresh or not burnham_path.exists() or burnham_path.stat().st_size < 100:
        fetch("https://www.gov.uk/government/people/andy-burnham", burnham_path)

    data = json.loads(api_path.read_text(encoding="utf-8"))
    parties: List[Dict[str, Any]] = []
    by_abbr: Dict[str, int] = {}
    for it in data.get("items") or []:
        v = it.get("value") or {}
        p = v.get("party") or {}
        abbr = p.get("abbreviation") or p.get("name") or "UNK"
        seats = int(v.get("total") or 0)
        row = {
            "name_en": p.get("name"),
            "abbr": abbr,
            "seats": seats,
            "male": v.get("male"),
            "female": v.get("female"),
            "party_id": p.get("id"),
        }
        parties.append(row)
        by_abbr[abbr] = seats
    parties.sort(key=lambda r: (-(r["seats"] or 0), r.get("name_en") or ""))

    burnham_html = burnham_path.read_text(encoding="utf-8", errors="ignore")
    pm_note = "불명"
    m = re.search(
        r"Andy Burnham became Prime Minister on ([^.<]+)\.?",
        strip_tags(burnham_html),
    )
    if m:
        pm_note = f"Andy Burnham became Prime Minister on {m.group(1).strip()}"

    # Floor/party leadership (curated from official + established roles; not full MP roster)
    floor_leadership = [
        {
            "office": "prime_minister",
            "name": "Andy Burnham",
            "party_abbr": "Lab",
            "chamber": "commons",
            "source": "https://www.gov.uk/government/people/andy-burnham",
            "as_of": "2026-07-20",
        },
        {
            "office": "leader_of_opposition",
            "name": "Kemi Badenoch",
            "party_abbr": "Con",
            "chamber": "commons",
            "source": "Conservatives official leadership (cross-check media); 불명 if contested",
            "confidence": "medium",
        },
        {
            "office": "speaker",
            "name": "불명",
            "party_abbr": "Spk",
            "chamber": "commons",
            "note": "Speaker seat counted separately in State of the Parties",
        },
    ]

    total = sum(p["seats"] for p in parties)
    return {
        "as_of": now_iso(),
        "query_date": date,
        "source": {
            "id": "uk_parliament_state_of_parties",
            "url": url,
            "govuk_pm": "https://www.gov.uk/government/people/andy-burnham",
            "grade": "official_api",
        },
        "summary": {
            "chamber": "house_of_commons",
            "seats_total": total,
            "by_party_abbr": by_abbr,
            "labour_majority_vs_326": (by_abbr.get("Lab") or 0) - 326,
            "pm_note": pm_note,
        },
        "parties": parties,
        "floor_leadership": floor_leadership,
        "lords": {
            "status": "todo",
            "note": "상원 좌석 추적은 후순위 (비선출)",
        },
        "null_policy": {"없음": "해당 없음", "불명": "출처 미확정"},
    }


def extract_isr_knesset(*, refresh: bool = True) -> Dict[str, Any]:
    raw_dir = RAW / "isr"
    wiki_path = raw_dir / "wiki_25th.html"
    url = "https://en.wikipedia.org/wiki/List_of_members_of_the_twenty-fifth_Knesset"
    if refresh or not wiki_path.exists() or wiki_path.stat().st_size < 1000:
        fetch(url, wiki_path)
    html = wiki_path.read_text(encoding="utf-8", errors="ignore")
    text = strip_tags(html)

    # Faction headers like "Likud (32)"
    patterns: List[Tuple[str, str]] = [
        (r"Likud\s*\((\d+)\)", "Likud"),
        (r"Yesh Atid\s*\((\d+)\)", "Yesh Atid"),
        (r"Shas\s*\((\d+)\)", "Shas"),
        (r"Blue and White\s*\((\d+)\)", "Blue and White"),
        (r"Religious Zionist Party\s*\((\d+)\)", "RZP"),
        (r"United Torah Judaism\s*\((\d+)\)", "UTJ"),
        (r"Otzma Yehudit\s*\((\d+)\)", "Otzma"),
        (r"Yisrael Beiteinu\s*\((\d+)\)", "YB"),
        (r"United Arab List\s*\((\d+)\)", "Ra'am"),
        (r"Hadash[–\-]Ta.?al\s*\((\d+)\)", "Hadash-Ta'al"),
        (r"New Hope\s*\((\d+)\)", "New Hope"),
        (r"\bLabor\s*\((\d+)\)", "Labor"),
        (r"\bNoam\s*\((\d+)\)", "Noam"),
        (r"National Unity\s*\((\d+)\)", "National Unity"),
        (r"The Democrats\s*\((\d+)\)", "Democrats"),
    ]
    by_abbr: Dict[str, int] = {}
    rows: List[Dict[str, Any]] = []
    for pat, abbr in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        seats = int(m.group(1))
        # keep first occurrence (faction header)
        if abbr in by_abbr:
            continue
        by_abbr[abbr] = seats
        rows.append({"abbr": abbr, "seats": seats})

    # Coalition status snippets from wiki text (medium confidence)
    coalition_hint = []
    for label in ("Governing coalition", "Opposition"):
        if label in text:
            coalition_hint.append(label)

    leaders = [
        {
            "office": "prime_minister",
            "name": "Benjamin Netanyahu",
            "party_abbr": "Likud",
            "chamber": "knesset",
            "source": url,
        },
        {
            "office": "leader_of_opposition",
            "name": "Yair Lapid",
            "party_abbr": "Yesh Atid",
            "chamber": "knesset",
            "source": url,
            "confidence": "medium",
        },
    ]

    seats_sum = sum(by_abbr.values())
    return {
        "as_of": now_iso(),
        "source": {
            "id": "wiki_25th_knesset",
            "url": url,
            "grade": "aggregator_wikipedia",
            "note": "25th Knesset live membership through end of term → 26th election 2026-10-27",
            "official_portal": "https://www.bechirot.gov.il/",
        },
        "summary": {
            "chamber": "knesset",
            "knesset_number": 25,
            "seats_total_nominal": 120,
            "seats_sum_parsed": seats_sum,
            "by_party_abbr": by_abbr,
            "parse_ok": seats_sum == 120,
        },
        "parties": sorted(rows, key=lambda r: (-r["seats"], r["abbr"])),
        "floor_leadership": leaders,
        "null_policy": {"없음": "해당 없음", "불명": "출처 미확정"},
    }


def merge_governance_polls(gbr: Dict[str, Any], isr: Dict[str, Any]) -> Dict[str, Any]:
    """Append/refresh GBR+ISR governance series; preserve other countries if file exists."""
    path = OUT / "governance_polls.json"
    existing: Dict[str, Any] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    series = [
        s
        for s in (existing.get("series") or [])
        if s.get("iso3") not in {"GBR", "ISR"}
    ]
    series.extend(
        [
            {
                "iso3": "GBR",
                "kind": "pm_approval",
                "subject": "Andy Burnham",
                "pollster": "More in Common (via Independent)",
                "net_approval": 19,
                "field_note": (
                    "Early premiership: Independent reports More in Common net +19 for Burnham "
                    "(post 2026-07-20 appointment). Classic approve/disapprove split 불명 in this pass."
                ),
                "sources": [
                    {
                        "url": "https://www.the-independent.com/news/uk/politics/andy-burnham-policies-tax-business-cost-living-energy-immigration-b3026552.html",
                        "label": "Independent: Burnham net +19 More in Common",
                    },
                    {
                        "url": "https://www.gov.uk/government/people/andy-burnham",
                        "label": "GOV.UK: PM since 20 July 2026",
                    },
                ],
                "confidence": "medium",
                "refresh": "weekly_uk_poll_aggregators",
            },
            {
                "iso3": "GBR",
                "kind": "pm_favourability_exit_snapshot",
                "subject": "Keir Starmer (former PM)",
                "pollster": "Ipsos",
                "approve_pct": 22,
                "disapprove_pct": 52,
                "field_date": "2026-07",
                "field_note": "Exit-period favourability, not current job approval. 17–22 July 2026 Ipsos Political Pulse.",
                "sources": [
                    {
                        "url": "https://www.ipsos.com/sites/default/files/ct/news/documents/2026-08/Ipsos_July%2026_Political_Pulse_v1d4_Int%20Use%20Only.pdf",
                        "label": "Ipsos Political Pulse July 2026",
                    }
                ],
                "confidence": "high",
                "refresh": "historical",
            },
            {
                "iso3": "ISR",
                "kind": "pm_preferred",
                "subject": "Benjamin Netanyahu",
                "pollster": "Midgam / Channel 12",
                "preferred_pm_pct": 38,
                "field_note": (
                    "Not classic job approval. Channel 12/Midgam preferred-PM: Netanyahu 38% vs Eisenkot 38% "
                    "(early Aug 2026). N12 suitability as low as 31% in separate wave — track range."
                ),
                "alt_preferred_pm_pct_range": [31, 38],
                "sources": [
                    {
                        "url": "https://www.timesofisrael.com/poll-shows-eisenkot-netanyahu-neck-and-neck-as-publics-preferred-option-for-pm/",
                        "label": "Times of Israel: Netanyahu–Eisenkot 38–38",
                    },
                    {
                        "url": "https://www.mako.co.il/news-politics/2026_q3/Article-fe6629e959cdf91026.htm",
                        "label": "N12 אולפן שישי: Netanyahu suitability ~31%",
                    },
                ],
                "confidence": "medium",
                "refresh": "weekly_il_tv_polls",
            },
        ]
    )
    return {
        "as_of": now_iso(),
        "policy": {
            "admit": [
                "presidential_job_approval",
                "cabinet_approval",
                "pm_approval",
                "pm_preferred",
            ],
            "reject": ["national_horserace_headline"],
        },
        "series": series,
        "gbr_context": {
            "commons_lab_seats": (gbr.get("summary") or {}).get("by_party_abbr", {}).get("Lab"),
        },
        "isr_context": {
            "knesset_likud_seats": (isr.get("summary") or {}).get("by_party_abbr", {}).get("Likud"),
        },
    }


def main() -> int:
    gbr = extract_gbr_commons(refresh=True)
    isr = extract_isr_knesset(refresh=True)
    polls = merge_governance_polls(gbr, isr)

    (OUT / "gbr_commons.json").write_text(
        json.dumps(gbr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "isr_knesset.json").write_text(
        json.dumps(isr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "governance_polls.json").write_text(
        json.dumps(polls, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # light touch summary merge
    summary_path = OUT / "summary.json"
    summary: Dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["generated_at"] = now_iso()
    summary["gbr"] = {
        "commons_by_party_abbr": (gbr.get("summary") or {}).get("by_party_abbr"),
        "seats_total": (gbr.get("summary") or {}).get("seats_total"),
        "floor_leadership": gbr.get("floor_leadership"),
        "pm_note": (gbr.get("summary") or {}).get("pm_note"),
    }
    summary["isr"] = {
        "knesset_by_party_abbr": (isr.get("summary") or {}).get("by_party_abbr"),
        "seats_sum_parsed": (isr.get("summary") or {}).get("seats_sum_parsed"),
        "floor_leadership": isr.get("floor_leadership"),
    }
    summary["polls"] = {
        "series": [
            {
                "iso3": s["iso3"],
                "kind": s["kind"],
                "approve_pct": s.get("approve_pct"),
                "net_approval": s.get("net_approval"),
                "preferred_pm_pct": s.get("preferred_pm_pct"),
                "pollster": s.get("pollster"),
                "field_date": s.get("field_date"),
            }
            for s in polls["series"]
        ]
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "gbr_seats": gbr["summary"]["seats_total"],
                "gbr_lab": gbr["summary"]["by_party_abbr"].get("Lab"),
                "gbr_pm": gbr["summary"]["pm_note"],
                "isr_sum": isr["summary"]["seats_sum_parsed"],
                "isr_likud": isr["summary"]["by_party_abbr"].get("Likud"),
                "polls": len(polls["series"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
