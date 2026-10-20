#!/usr/bin/env python3
"""Regenerate the Israel research board from preserved reviewed inputs only."""
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from election_watch.israel_analysis import build, health, read_inputs

ROOT = Path(__file__).resolve().parent


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'config/israel/2026')
    parser.add_argument('--output', type=Path, default=ROOT.parents[1] / 'public/data/israel_election_analysis_v1.json')
    parser.add_argument('--as-of', default='2026-10-20', help='Evidence date; rebuilding cannot advance it')
    parser.add_argument('--built-at', default=None)
    parser.add_argument('--check', action='store_true', help='Validate and compare existing generated files')
    args = parser.parse_args()
    status_path = args.output.with_name('israel_election_analysis_status_v1.json')
    # Complete validation precedes all publication. A malformed replay cannot
    # replace the last good board or advance its original evidence timestamp.
    built_at = args.built_at
    if args.check and built_at is None:
        built_at = json.loads(args.output.read_text())['built_at']
    board = build(read_inputs(args.input_dir), args.as_of,
                  built_at or datetime.now(timezone.utc).isoformat())
    status = health(board)
    if args.check:
        if json.loads(args.output.read_text()) != board or json.loads(status_path.read_text()) != status:
            raise ValueError('generated Israel files differ from reviewed inputs')
    else:
        atomic(args.output, board)
        atomic(status_path, status)
    print(json.dumps(board['coverage'], ensure_ascii=False))


if __name__ == '__main__':
    main()
