"""Orchestrate QRA download → parse → tables → causal JSON."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from .causal import auctions_to_issuance_components, build_causal_pack
from .compare import build_net_borrowing_compare, build_quarter_history
from .fetch import (
    ArchiveDoc,
    discover_archives,
    discover_most_recent_assets,
    download_docs,
    download_url,
    slug_from_url,
)
from .fiscaldata import fetch_fiscal_overlay
from .parse import parse_doc
from .tables_pdf import (
    extract_pdf_links_from_html,
    parse_sources_uses_pdf,
    parse_tbac_financing_pdf,
)

ENGINE_VERSION = "0.3.0"
TYPICAL_ANNOUNCE_MONTHS = (2, 5, 8, 11)


def _docs_from_manifest(cache_dir: Path, *, from_year: int, to_year: int) -> List[ArchiveDoc]:
    path = cache_dir / "manifest.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    out: List[ArchiveDoc] = []
    for url, meta in raw.items():
        if meta.get("error"):
            continue
        year = int(meta.get("year") or 0)
        if not (from_year <= year <= to_year):
            continue
        out.append(
            ArchiveDoc(
                kind=meta.get("kind") or "financing_estimates",
                year=year,
                quarter=meta.get("quarter"),
                url=url,
                label=meta.get("label") or url,
            )
        )
    return sorted(out, key=lambda x: (x.year, x.quarter or 0, x.kind), reverse=True)


def default_cache_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "cache" / "qra"


def default_out_path() -> Path:
    return Path(__file__).resolve().parents[4] / "public" / "data" / "qra_engine_v1.json"


def _event_key(year: int, quarter: Optional[int]) -> str:
    return f"{year}-Q{quarter or 0}"


def _pdf_fname(url: str) -> str:
    name = unquote(Path(urlparse(url).path).name)
    name = re.sub(r"[^\w.\-]+", "_", name)
    return name or "doc.pdf"


def _attach_pdfs_for_event(
    *,
    key: str,
    html_path: Path,
    pdf_dir: Path,
    download: bool,
    force: bool,
) -> Dict[str, Any]:
    """Download/parse Sources-Uses (+ any TBAC) linked from an estimates HTML page."""
    html = html_path.read_text(errors="replace")
    links = extract_pdf_links_from_html(html)
    out: Dict[str, Any] = {"pdf_urls": {}, "sources_uses": None, "tbac_financing": None}
    for kind, url in links:
        out["pdf_urls"][kind] = url
        dest = pdf_dir / _pdf_fname(url)
        if download:
            download_url(url, dest, force=force)
        if not dest.exists():
            continue
        if kind == "sources_uses":
            try:
                table = parse_sources_uses_pdf(dest)
                out["sources_uses"] = table.to_dict()
                print(f"  sources_uses {key} rows={len(table.rows)} ok={table.parse_ok}", flush=True)
            except Exception as exc:  # noqa: BLE001
                out["sources_uses"] = {"parse_ok": False, "error": str(exc), "source_pdf": dest.name}
        elif kind == "tbac_financing":
            try:
                table = parse_tbac_financing_pdf(dest)
                out["tbac_financing"] = table.to_dict()
            except Exception as exc:  # noqa: BLE001
                out["tbac_financing"] = {"parse_ok": False, "error": str(exc), "source_pdf": dest.name}
    return out


def _download_most_recent_tbac(pdf_dir: Path, *, force: bool = False) -> Optional[Dict[str, Any]]:
    try:
        assets = discover_most_recent_assets()
    except Exception as exc:  # noqa: BLE001
        print(f"  most-recent discover fail: {exc}", flush=True)
        return None
    for label, url in assets:
        low = (label + " " + url).lower()
        if "recommended financing" in low or "tbacrecommendedfinancing" in low.replace("_", ""):
            dest = pdf_dir / _pdf_fname(url)
            download_url(url, dest, force=force)
            if dest.exists():
                try:
                    return parse_tbac_financing_pdf(dest).to_dict()
                except Exception as exc:  # noqa: BLE001
                    return {"parse_ok": False, "error": str(exc), "url": url}
    return None


def build_qra_engine(
    *,
    from_year: int = 2020,
    to_year: int = 2099,
    cache_dir: Optional[Path] = None,
    download: bool = True,
    force_download: bool = False,
    out_path: Optional[Path] = None,
    fiscal: bool = True,
) -> Dict[str, Any]:
    cache_dir = cache_dir or default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = cache_dir / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    if download:
        docs = discover_archives(from_year=from_year, to_year=to_year)
    else:
        docs = _docs_from_manifest(cache_dir, from_year=from_year, to_year=to_year)
        if not docs:
            docs = discover_archives(from_year=from_year, to_year=to_year)
    print(f"discovered {len(docs)} archive docs (>= {from_year})", flush=True)

    if download:
        paths = download_docs(docs, cache_dir, force=force_download)
    else:
        paths = {}
        for d in docs:
            slug = slug_from_url(d.url)
            p = cache_dir / "html" / d.kind / str(d.year) / f"Q{d.quarter or 0}_{slug}.html"
            if p.exists():
                paths[d.url] = p

    by_event: Dict[str, Dict[str, Any]] = defaultdict(dict)
    parse_failures: List[str] = []

    for d in docs:
        path = paths.get(d.url)
        if not path or not path.exists():
            parse_failures.append(f"missing:{d.url}")
            continue
        html = path.read_text(errors="replace")
        parsed = parse_doc(html, kind=d.kind, url=d.url, year=d.year, quarter=d.quarter)
        key = _event_key(d.year, d.quarter)
        slot = "estimates" if d.kind == "financing_estimates" else "policy"
        by_event[key][slot] = parsed.to_dict()
        by_event[key]["year"] = d.year
        by_event[key]["quarter"] = d.quarter
        by_event[key].setdefault("urls", {})[slot] = d.url
        if not parsed.parse_ok:
            parse_failures.append(f"empty:{d.kind}:{key}:{d.url}")

        if d.kind == "financing_estimates":
            pdf_blob = _attach_pdfs_for_event(
                key=key,
                html_path=path,
                pdf_dir=pdf_dir,
                download=download,
                force=force_download,
            )
            by_event[key]["sources_uses"] = pdf_blob.get("sources_uses")
            if pdf_blob.get("tbac_financing"):
                by_event[key]["tbac_financing"] = pdf_blob["tbac_financing"]
            by_event[key].setdefault("urls", {}).update(pdf_blob.get("pdf_urls") or {})

    # Latest TBAC recommended financing from most-recent documents page
    latest_tbac = None
    if download:
        latest_tbac = _download_most_recent_tbac(pdf_dir, force=force_download)
        if latest_tbac and latest_tbac.get("parse_ok"):
            # attach to newest event if missing
            newest = sorted(by_event.keys(), reverse=True)[0] if by_event else None
            if newest and not by_event[newest].get("tbac_financing"):
                by_event[newest]["tbac_financing"] = latest_tbac

    # Build event list oldest→newest first for prior_event lookup, then reverse for output
    keys_asc = sorted(by_event.keys(), key=lambda k: (by_event[k].get("year") or 0, by_event[k].get("quarter") or 0))
    events_asc: List[Dict[str, Any]] = []
    su_ok = 0
    tbac_ok = 0
    for key in keys_asc:
        blob = by_event[key]
        causal = build_causal_pack(blob)
        policy = blob.get("policy") or {}
        components = auctions_to_issuance_components(policy.get("auctions") or [])
        tbac = blob.get("tbac_financing") or {}
        if tbac.get("parse_ok") and tbac.get("qra_issuance_components"):
            components = tbac["qra_issuance_components"]
            tbac_ok += 1
        su = blob.get("sources_uses")
        if su and su.get("parse_ok"):
            su_ok += 1
            revs = [r for r in (su.get("rows") or []) if r.get("row_kind") == "revisions"]
            if revs:
                r0 = revs[-1]
                vs = r0.get("marketable_borrowing_bn")
                if vs is not None and abs(vs) >= 25:
                    causal.setdefault("flags", [])
                    if vs > 0 and "su_marketable_revision_up" not in causal["flags"]:
                        causal["flags"].append("su_marketable_revision_up")
                    if vs < 0 and "su_marketable_revision_down" not in causal["flags"]:
                        causal["flags"].append("su_marketable_revision_down")

        prior_ev = events_asc[-1] if events_asc else None
        draft = {
            "id": key,
            "year": blob.get("year"),
            "quarter": blob.get("quarter"),
            "urls": blob.get("urls") or {},
            "estimates": blob.get("estimates"),
            "policy": blob.get("policy"),
            "sources_uses": su,
            "tbac_financing": tbac or None,
            "causal": causal,
            "qra_issuance_components": components,
            "tables": {
                "sources_uses_rows": (su or {}).get("rows") if su else [],
                "tbac_recommendation_months": (tbac or {}).get("recommendation_months")
                if tbac
                else [],
            },
        }
        draft["compare"] = build_net_borrowing_compare(draft, prior_event=prior_ev)
        events_asc.append(draft)

    events = list(reversed(events_asc))
    history = build_quarter_history(events_asc)

    latest = next((e for e in events if (e.get("estimates") or {}).get("parse_ok")), None)
    if latest is None:
        latest = events[0] if events else None

    fiscal_overlay = None
    if fiscal:
        try:
            print("  fiscaldata overlay", flush=True)
            fiscal_overlay = fetch_fiscal_overlay()
        except Exception as exc:  # noqa: BLE001
            fiscal_overlay = {"ok": False, "errors": [str(exc)]}

    # Compare latest QRA cash assumption vs live TGA
    tga_gap = None
    if fiscal_overlay and (fiscal_overlay.get("tga") or {}).get("latest_bn") is not None and latest:
        su = latest.get("sources_uses") or {}
        est_rows = [
            r
            for r in (su.get("rows") or [])
            if r.get("row_kind") == "estimate" and r.get("end_cash_balance_bn") is not None
        ]
        if est_rows:
            # prefer current-quarter estimate (first upcoming / latest announce)
            qra_cash = est_rows[-1].get("end_cash_balance_bn")
            # better: take estimate with latest announcement date for near-term quarter
            for r in reversed(est_rows):
                if r.get("announcement_date"):
                    qra_cash = r.get("end_cash_balance_bn")
                    # Jul-Sep style current if possible
                    if "Jul" in (r.get("period") or "") or "Apr" in (r.get("period") or ""):
                        break
            live = fiscal_overlay["tga"]["latest_bn"]
            tga_gap = {
                "tga_actual_bn": live,
                "qra_end_cash_bn": qra_cash,
                "gap_bn": round(live - float(qra_cash), 3) if qra_cash is not None else None,
                "tga_asof": fiscal_overlay["tga"].get("asof"),
            }

    payload: Dict[str, Any] = {
        "schema_version": "qra-engine-v1",
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "from_year": from_year,
        "source": {
            "kind": "treasury_archives_plus_pdf_tables",
            "archives": [
                "quarterly-refunding-financing-estimates-by-calendar-year",
                "official-remarks-on-quarterly-refunding-by-calendar-year",
                "most-recent-quarterly-refunding-documents",
            ],
            "fiscaldata": bool(fiscal_overlay and fiscal_overlay.get("ok")),
        },
        "stats": {
            "docs_discovered": len(docs),
            "docs_downloaded": len(paths),
            "events": len(events),
            "parse_failures": len(parse_failures),
            "parse_ok_estimates": sum(1 for e in events if (e.get("estimates") or {}).get("parse_ok")),
            "parse_ok_policy": sum(1 for e in events if (e.get("policy") or {}).get("parse_ok")),
            "parse_ok_sources_uses": su_ok,
            "parse_ok_tbac": tbac_ok,
        },
        "parse_failures_sample": parse_failures[:40],
        "fiscal": fiscal_overlay,
        "tga_vs_qra": tga_gap,
        "latest": {
            "id": latest["id"] if latest else None,
            "summary_ko": (latest.get("causal") or {}).get("summary_ko") if latest else None,
            "flags": (latest.get("causal") or {}).get("flags") if latest else [],
            "qra_issuance_components": (latest or {}).get("qra_issuance_components") or [],
            "compare": (latest or {}).get("compare"),
            "estimates_quarters": ((latest or {}).get("estimates") or {}).get("quarters") or [],
            "sources_uses_latest_estimates": ((latest or {}).get("sources_uses") or {}).get(
                "latest_estimates"
            )
            or [],
            "tbac_recommendation_months": (
                ((latest or {}).get("tbac_financing") or {}).get("recommendation_months") or []
            ),
            "urls": (latest or {}).get("urls") or {},
            "tables": (latest or {}).get("tables") or {},
        },
        "history_net_borrowing": history,
        "events": events,
        "schedule_note_ko": (
            "QRA는 보통 2·5·8·11월 환급주간에 공시된다. "
            "`python3 build_qra_engine.py --download` 가 Estimates HTML + Sources&Uses PDF + "
            "TBAC 표 + Fiscal Data(TGA/관세)를 갱신한다."
        ),
        "typical_announce_months": list(TYPICAL_ANNOUNCE_MONTHS),
    }

    out_path = out_path or default_out_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {out_path} events={len(events)} "
        f"est_ok={payload['stats']['parse_ok_estimates']} "
        f"su_ok={su_ok} tbac_ok={tbac_ok}",
        flush=True,
    )
    return payload


def load_latest_issuance(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = path or default_out_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    latest = data.get("latest") or {}
    comps = latest.get("qra_issuance_components") or []
    if not comps:
        return None
    return {
        "components": comps,
        "asof": data.get("generated_at"),
        "summary_ko": latest.get("summary_ko"),
        "source": "qra_engine_v1",
        "event_id": latest.get("id"),
        "urls": latest.get("urls") or {},
        "quarters": latest.get("estimates_quarters") or [],
        "sources_uses": latest.get("sources_uses_latest_estimates") or [],
        "tbac": latest.get("tbac_recommendation_months") or [],
        "tga_vs_qra": data.get("tga_vs_qra"),
        "compare": latest.get("compare"),
        "history_net_borrowing": data.get("history_net_borrowing") or [],
        "flags": latest.get("flags") or [],
    }
