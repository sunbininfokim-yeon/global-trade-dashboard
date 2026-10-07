#!/usr/bin/env python3
"""Apply the reviewed display roster without touching poll admission or other countries."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from election_watch.federal_matchups import attach_matchups

ROOT = Path(__file__).resolve().parent


def publish(snapshot_path, board_path, as_of):
    snapshot = json.loads(Path(snapshot_path).read_text())
    board_path = Path(board_path)
    board = json.loads(board_path.read_text())
    usa = [c for c in board['countries'] if c['iso3'] == 'USA']
    if len(usa) != 1:
        raise ValueError('Expected one USA board')
    states = usa[0]['ui_ready']['state_drilldown']['states']
    usa[0]['ui_ready']['state_drilldown']['states'] = attach_matchups(states, snapshot, as_of)
    content = json.dumps(board, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=board_path.parent, delete=False) as f:
            temp = f.name
            f.write(content)
        os.replace(temp, board_path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
    return len(snapshot['races'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'config/federal_matchups/2026.json')
    parser.add_argument('--board', type=Path, default=ROOT.parent.parent / 'public/data/elections_board_v1.json')
    parser.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()
    print(f'Published {publish(args.snapshot, args.board, args.as_of)} reviewed display matchups')
