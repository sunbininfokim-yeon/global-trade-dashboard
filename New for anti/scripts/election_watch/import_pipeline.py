#!/usr/bin/env python3
"""Import election_watch pipeline + learning artifacts into a dest clone.

Use this to pull Cursor/Grok work into `New for anti-dart` (or any sibling clone)
without inventing dates or wiping dest-only files.

Examples:

  # Inventory only
  python3 import_pipeline.py --dest "/Users/yeoninair/Documents/New for anti-dart" --dry-run

  # Copy pipeline + learning JSON (skip raw HTML/PDF cache)
  python3 import_pipeline.py --dest "/Users/yeoninair/Documents/New for anti-dart"

  # Later: drop Grok JSON notes into a folder, then
  python3 import_pipeline.py --dest "..." --grok-pack "/path/to/grok_export"
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE_REPO = HERE.parents[2]  # .../New for anti  (repo root)

SKIP_DIR_NAMES = {"__pycache__", ".git"}
SKIP_FILE_NAMES = {".DS_Store"}

PUBLIC_ELECTION_NAMES = [
    "elections_board_v1.json",
    "elections_calendar_master_v1.json",
    "invest_lens_elections.json",
    "race_progress_bundle_v1.json",
    "race_progress_kor_v1.json",
    "race_progress_usa_v1.json",
    "race_aggregation_compare_v1.json",
    "race_progress_preview.html",
]

SCAFFOLD_MARKERS = (
    "(집권) 여당",
    "Incumbent party",
    "election_watch_seed_v1",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _is_scaffold_text(text: str) -> bool:
    return any(m in text for m in SCAFFOLD_MARKERS)


def _json_as_of(obj: Any) -> str:
    if not isinstance(obj, dict):
        return ""
    for k in ("as_of", "as_of_date", "generated_at", "as_of_iso"):
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _richness(obj: Any) -> int:
    """Cheap structural score — more keys/rows wins when dates tie."""
    if isinstance(obj, dict):
        n = len(obj)
        for v in obj.values():
            n += _richness(v)
        return n
    if isinstance(obj, list):
        return len(obj) + sum(_richness(x) for x in obj[:50])
    if obj in (None, "", "불명", "없음"):
        return 0
    return 1


def decide_overwrite(src: Path, dest: Path) -> Tuple[str, str]:
    """Return (action, reason). action in copy|skip|overwrite."""
    if not dest.exists():
        return "copy", "dest missing"
    if src.suffix.lower() not in {".json", ".jsonl", ".md", ".py", ".html", ".htm", ".txt"}:
        if src.stat().st_mtime > dest.stat().st_mtime + 1:
            return "overwrite", "source mtime newer (non-json)"
        return "skip", "dest exists, source not newer"

    try:
        src_text = src.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return "skip", f"cannot read source: {e}"
    try:
        dest_text = dest.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return "overwrite", f"dest unreadable ({e})"

    if _is_scaffold_text(dest_text) and not _is_scaffold_text(src_text):
        return "overwrite", "dest is scaffold; source is filled"

    if src.suffix.lower() == ".json":
        try:
            src_obj = json.loads(src_text)
            dest_obj = json.loads(dest_text)
        except json.JSONDecodeError:
            if len(src_text) > len(dest_text) * 1.2:
                return "overwrite", "dest JSON invalid or smaller"
            return "skip", "JSON parse mismatch; keep dest"
        src_asof, dest_asof = _json_as_of(src_obj), _json_as_of(dest_obj)
        src_r, dest_r = _richness(src_obj), _richness(dest_obj)
        if dest_asof and src_asof and dest_asof > src_asof and dest_r >= src_r:
            return "skip", f"dest as_of newer ({dest_asof} > {src_asof})"
        if src_r > dest_r:
            return "overwrite", f"source richer ({src_r} > {dest_r})"
        if src_asof and dest_asof and src_asof > dest_asof:
            return "overwrite", f"source as_of newer ({src_asof} > {dest_asof})"
        if src_text == dest_text:
            return "skip", "identical"
        if dest_r > src_r:
            return "skip", f"dest richer ({dest_r} > {src_r}); keep dest"
        return "skip", "same richness; keep dest (no delete/guess)"

    if len(src_text) > len(dest_text) * 1.15:
        return "overwrite", "source text substantially larger"
    if src_text == dest_text:
        return "skip", "identical"
    return "skip", "dest exists; not clearly weaker"


def iter_watch_files(src_watch: Path, *, include_raw: bool) -> List[Path]:
    out: List[Path] = []
    for p in src_watch.rglob("*"):
        if not p.is_file():
            continue
        if p.name in SKIP_FILE_NAMES:
            continue
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue
        rel = p.relative_to(src_watch)
        if not include_raw and (rel.parts[0] == "raw" or "raw" in rel.parts):
            continue
        out.append(p)
    return sorted(out)


def copy_file(src: Path, dest: Path, *, dry_run: bool) -> None:
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def ingest_grok_pack(pack: Path, dest_watch: Path, *, dry_run: bool) -> Dict[str, Any]:
    """Park Grok export JSON under extracted/grok_ingest/. Do not merge calendars blindly."""
    dest_dir = dest_watch / "config" / "extracted" / "grok_ingest"
    files = [p for p in pack.rglob("*") if p.is_file() and p.suffix.lower() in {".json", ".jsonl", ".md"}]
    copied = []
    for p in files:
        dest = dest_dir / p.relative_to(pack)
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        copied.append(str(p.relative_to(pack)))
    note = (
        "Grok pack copied as inventory only. "
        "Do not auto-merge into calendars/profiles: dates need official URL + grade. "
        "Next: review grok_ingest/ then patch config/calendars/{iso}_2026.json by hand."
    )
    return {"copied": copied, "dest": str(dest_dir), "note": note}


def main() -> int:
    p = argparse.ArgumentParser(description="Import election_watch pipeline into a dest clone")
    p.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_REPO,
        help="Repo root that already has the filled pipeline (Documents/New for anti)",
    )
    p.add_argument(
        "--dest",
        type=Path,
        required=True,
        help="Repo root to receive files (Documents/New for anti-dart)",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--include-raw", action="store_true", help="Also copy raw/ HTML-PDF cache (~18MB)")
    p.add_argument(
        "--no-public",
        action="store_true",
        help="Skip public/data election JSON (board + race_progress)",
    )
    p.add_argument(
        "--grok-pack",
        type=Path,
        default=None,
        help="Optional folder of Grok export JSON/MD to park under grok_ingest/",
    )
    args = p.parse_args()

    src_root = args.source.resolve()
    dest_root = args.dest.resolve()
    src_watch = src_root / "New for anti" / "scripts" / "election_watch"
    dest_watch = dest_root / "New for anti" / "scripts" / "election_watch"
    src_pub = src_root / "New for anti" / "public" / "data"
    dest_pub = dest_root / "New for anti" / "public" / "data"
    src_elec_cfg = src_root / "New for anti" / "scripts" / "commodity_news" / "config" / "elections.json"
    dest_elec_cfg = dest_root / "New for anti" / "scripts" / "commodity_news" / "config" / "elections.json"

    if not src_watch.is_dir():
        raise SystemExit(f"source election_watch missing: {src_watch}")
    if src_root == dest_root:
        raise SystemExit("source and dest are the same path")

    report: Dict[str, Any] = {
        "schema": "election_import_report_v1",
        "generated_at": _now(),
        "source": str(src_root),
        "dest": str(dest_root),
        "dry_run": bool(args.dry_run),
        "actions": [],
        "counts": {"copy": 0, "overwrite": 0, "skip": 0},
    }

    for src in iter_watch_files(src_watch, include_raw=args.include_raw):
        rel = src.relative_to(src_watch)
        dest = dest_watch / rel
        action, reason = decide_overwrite(src, dest)
        report["actions"].append(
            {"path": str(Path("New for anti/scripts/election_watch") / rel), "action": action, "reason": reason}
        )
        report["counts"][action] = report["counts"].get(action, 0) + 1
        if action in {"copy", "overwrite"}:
            copy_file(src, dest, dry_run=args.dry_run)

    if not args.no_public:
        for name in PUBLIC_ELECTION_NAMES:
            src = src_pub / name
            if not src.exists():
                report["actions"].append({"path": f"public/data/{name}", "action": "skip", "reason": "source missing"})
                report["counts"]["skip"] += 1
                continue
            dest = dest_pub / name
            action, reason = decide_overwrite(src, dest)
            report["actions"].append(
                {"path": f"New for anti/public/data/{name}", "action": action, "reason": reason}
            )
            report["counts"][action] = report["counts"].get(action, 0) + 1
            if action in {"copy", "overwrite"}:
                copy_file(src, dest, dry_run=args.dry_run)

    if src_elec_cfg.exists():
        action, reason = decide_overwrite(src_elec_cfg, dest_elec_cfg)
        report["actions"].append(
            {
                "path": "New for anti/scripts/commodity_news/config/elections.json",
                "action": action,
                "reason": reason,
            }
        )
        report["counts"][action] = report["counts"].get(action, 0) + 1
        if action in {"copy", "overwrite"}:
            copy_file(src_elec_cfg, dest_elec_cfg, dry_run=args.dry_run)

    if args.grok_pack:
        pack = args.grok_pack.resolve()
        if not pack.is_dir():
            raise SystemExit(f"--grok-pack is not a directory: {pack}")
        report["grok_pack"] = ingest_grok_pack(pack, dest_watch, dry_run=args.dry_run)

    # Always write report on dest (unless dry-run: print only)
    report_path = dest_watch / "config" / "extracted" / "import_report_v1.json"
    print(json.dumps(report["counts"], ensure_ascii=False))
    print("source", src_watch)
    print("dest  ", dest_watch)
    if args.dry_run:
        print("dry-run: no files written")
    else:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
