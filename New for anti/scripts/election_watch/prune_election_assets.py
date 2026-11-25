#!/usr/bin/env python3
"""One-off and manual cleanup of superseded hashed election assets.

Dry run by default. ``--previous-root`` takes the previous generation of an
index (``git show <older-sha>:<index>``); files it reaches are retained, the
same one-generation rule the generators apply.
"""
import argparse
import json
from pathlib import Path
from election_watch.asset_prune import FOLDERS, prune, stale

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, default=ROOT.parent.parent / 'public/data')
    parser.add_argument('--folder', choices=FOLDERS, action='append')
    parser.add_argument('--previous-root', type=Path, action='append', default=[])
    parser.add_argument('--apply', action='store_true', help='delete (default: report only)')
    args = parser.parse_args()
    previous = [json.loads(p.read_text(encoding='utf-8')) for p in args.previous_root]
    for folder in args.folder or FOLDERS:
        total = sum(1 for _ in (args.public / folder).rglob('*.json'))
        removed = (prune if args.apply else stale)(args.public, folder, previous)
        print(json.dumps({'folder': folder, 'files': total, 'stale': len(removed),
                          'remaining': total - len(removed), 'applied': args.apply}))


if __name__ == '__main__':
    main()
