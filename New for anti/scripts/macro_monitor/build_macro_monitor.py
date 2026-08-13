#!/usr/bin/env python3
"""Build public/data/macro_monitor_v1.json for the Macro Monitor prototype."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.engine import build_universe  # noqa: E402

DEFAULT_COUNTRIES = ROOT / "config" / "countries.json"
DEFAULT_SERIES = ROOT / "config" / "series.spec.json"
DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser(description="Macro Monitor country snapshot builder")
    ap.add_argument("--countries", type=Path, default=DEFAULT_COUNTRIES)
    ap.add_argument("--series", type=Path, default=DEFAULT_SERIES)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--asof", type=str, default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--print-stats", action="store_true")
    ap.add_argument(
        "--live",
        action="store_true",
        help="Overlay live FRED CSV / Yahoo / BOK Worker onto fixture snapshot",
    )
    args = ap.parse_args()

    countries_doc = json.loads(args.countries.read_text(encoding="utf-8"))
    series_doc = json.loads(args.series.read_text(encoding="utf-8"))
    asof = date.fromisoformat(args.asof) if args.asof else date.today()

    doc = build_universe(
        countries_doc,
        series_doc,
        asof=asof,
        generated_at=_now(),
    )

    if args.live:
        from macro_monitor.live_overlay import overlay_live  # noqa: WPS433

        stats = overlay_live(doc, asof=asof)
        if args.print_stats:
            print(f"live ok={len(stats['ok'])} fail={len(stats['fail'])} skip={len(stats['skip'])}")
            for x in stats["ok"][:40]:
                print("  OK", x)
            for x in stats["fail"][:20]:
                print("  FAIL", x)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: Infinity/NaN are not valid JSON — fail the build instead
    # of writing a file browsers/Workers cannot parse.
    try:
        payload = json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False)
    except ValueError as exc:
        raise SystemExit(
            f"refusing to write non-JSON numbers (Infinity/NaN): {exc}"
        ) from exc
    args.output.write_text(payload + "\n", encoding="utf-8")

    if args.print_stats:
        n = len(doc["countries"])
        inds = sum(len(c["indicators"]) for c in doc["countries"])
        usa = next(c for c in doc["countries"] if c["iso3"] == "USA")
        jpn = next(c for c in doc["countries"] if c["iso3"] == "JPN")
        print(f"wrote {args.output}")
        print(f"countries={n} indicators={inds}")
        print(f"USA kit={usa['kit']} cats={usa['active_categories']} n={len(usa['indicators'])}")
        for h in usa["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        net = next(i for i in usa["indicators"] if i["id"] == "net_liquidity")
        print(f"  net_liquidity={net['display']} derived={net.get('derived')}")
        print(f"JPN kit={jpn['kit']} cats={jpn['active_categories']} n={len(jpn['indicators'])}")
        for h in jpn["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        gbr = next(c for c in doc["countries"] if c["iso3"] == "GBR")
        print(f"GBR kit={gbr['kit']} cats={gbr['active_categories']} n={len(gbr['indicators'])}")
        for h in gbr["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        chn = next(c for c in doc["countries"] if c["iso3"] == "CHN")
        print(f"CHN kit={chn['kit']} cats={chn['active_categories']} n={len(chn['indicators'])}")
        for h in chn["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        emu = next(c for c in doc["countries"] if c["iso3"] == "EMU")
        print(f"EMU kit={emu['kit']} cats={emu['active_categories']} n={len(emu['indicators'])}")
        for h in emu["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        rus = next(c for c in doc["countries"] if c["iso3"] == "RUS")
        print(f"RUS kit={rus['kit']} cats={rus['active_categories']} n={len(rus['indicators'])}")
        for h in rus["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        hkg = next(c for c in doc["countries"] if c["iso3"] == "HKG")
        print(f"HKG kit={hkg['kit']} cats={hkg['active_categories']} n={len(hkg['indicators'])}")
        for h in hkg["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        sgp = next(c for c in doc["countries"] if c["iso3"] == "SGP")
        print(f"SGP kit={sgp['kit']} cats={sgp['active_categories']} n={len(sgp['indicators'])}")
        for h in sgp["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        zaf = next(c for c in doc["countries"] if c["iso3"] == "ZAF")
        print(f"ZAF kit={zaf['kit']} cats={zaf['active_categories']} n={len(zaf['indicators'])}")
        for h in zaf["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        ind = next(c for c in doc["countries"] if c["iso3"] == "IND")
        print(f"IND kit={ind['kit']} cats={ind['active_categories']} n={len(ind['indicators'])}")
        for h in ind["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        isr = next(c for c in doc["countries"] if c["iso3"] == "ISR")
        print(f"ISR kit={isr['kit']} cats={isr['active_categories']} n={len(isr['indicators'])}")
        for h in isr["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        kor = next(c for c in doc["countries"] if c["iso3"] == "KOR")
        print(f"KOR kit={kor['kit']} cats={kor['active_categories']} n={len(kor['indicators'])}")
        for h in kor["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        can = next(c for c in doc["countries"] if c["iso3"] == "CAN")
        print(f"CAN kit={can['kit']} cats={can['active_categories']} n={len(can['indicators'])}")
        for h in can["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        aus = next(c for c in doc["countries"] if c["iso3"] == "AUS")
        print(f"AUS kit={aus['kit']} cats={aus['active_categories']} n={len(aus['indicators'])}")
        for h in aus["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        che = next(c for c in doc["countries"] if c["iso3"] == "CHE")
        print(f"CHE kit={che['kit']} cats={che['active_categories']} n={len(che['indicators'])}")
        for h in che["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        bra = next(c for c in doc["countries"] if c["iso3"] == "BRA")
        print(f"BRA kit={bra['kit']} cats={bra['active_categories']} n={len(bra['indicators'])}")
        for h in bra["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        vnm = next(c for c in doc["countries"] if c["iso3"] == "VNM")
        print(f"VNM kit={vnm['kit']} cats={vnm['active_categories']} n={len(vnm['indicators'])}")
        for h in vnm["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        kaz = next(c for c in doc["countries"] if c["iso3"] == "KAZ")
        print(f"KAZ kit={kaz['kit']} cats={kaz['active_categories']} n={len(kaz['indicators'])}")
        for h in kaz["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")
        twn = next(c for c in doc["countries"] if c["iso3"] == "TWN")
        print(f"TWN kit={twn['kit']} cats={twn['active_categories']} n={len(twn['indicators'])}")
        for h in twn["headlines"]:
            print(f"  headline: {h['label_ko']} {h['display']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
