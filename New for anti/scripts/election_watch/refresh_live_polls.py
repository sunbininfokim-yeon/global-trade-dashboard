#!/usr/bin/env python3
"""Refresh selected US polls; preserve previous data on transport/schema failure."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from election_watch.polls import read, atomic
from election_watch.live_polls import apply_watchlist, build_live, fetch_polls, validated_results

ROOT = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--policy', type=Path, default=ROOT/'config/usa_polls/live_2026.json')
    p.add_argument('--watchlist', type=Path, default=ROOT/'config/usa_polls/watchlist_2026.json')
    p.add_argument('--results', type=Path, default=ROOT/'config/usa_polls/results_2026.json')
    p.add_argument('--output', type=Path, default=ROOT.parent.parent/'public/data/usa_election_live_polls_v1.json')
    p.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    p.add_argument('--input', type=Path, help='Replay saved provider response for testing; marked as replay')
    args = p.parse_args()
    checked = datetime.now(timezone.utc).isoformat()
    health = args.output.with_name('usa_election_live_polls_status_v1.json')
    try:
        policy = apply_watchlist(read(args.policy), read(args.watchlist))
        rows, url = (read(args.input), 'replay') if args.input else fetch_polls(policy['cycle'], args.as_of)
        board = build_live(rows, policy, read(args.results), args.as_of, checked, url)
        if args.input:
            board['source_status'] = 'replay'
        atomic(args.output, board)
        atomic(health, {'checked_at': checked, 'status': board['source_status'], 'as_of': args.as_of})
        print(board['coverage'])
        print({d: {s: sum(r['windows'][d]['status'] == s for r in board['races'].values())
                   for s in ('poll_lead','no_recent_poll','insufficient_pollsters','tie')} for d in ('7','14')})
    except Exception as exc:
        # Official outcomes are independent of the poll transport. If the API
        # fails, still accept a newly reviewed result without refreshing polls.
        try:
            existing = read(args.output)
            policy = apply_watchlist(read(args.policy), read(args.watchlist))
            confirmed = validated_results(read(args.results), policy, args.as_of)
            changed = False
            for rid, race in existing.get('races', {}).items():
                result = confirmed.get(rid)
                if race.get('result') != result:
                    race['result'] = result
                    changed = True
            if changed:
                atomic(args.output, existing)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        atomic(health, {'checked_at': checked, 'status': 'error', 'error_type': type(exc).__name__,
                        'note_ko': '수집 실패. 마지막 정상 자료를 보존하며 지도 색상은 중립 처리합니다.'})
        print('Poll refresh failed:', type(exc).__name__)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
