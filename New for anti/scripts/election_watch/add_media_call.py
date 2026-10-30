#!/usr/bin/env python3
"""Record one election-night media call (AP 등) in the hand-reviewed calls file.

  python3 add_media_call.py USA:PA:governor "Josh Shapiro" DEM --by AP --at 2026-11-04T01:12Z --url https://apnews.com/...
  python3 add_media_call.py USA:GA:senate --runoff --by AP --at ... --url ...
  python3 add_media_call.py USA:AZ:senate --retract --by AP --at ... --url ...

Validates the whole file (race, party, time window, https source, certified
conflict) and refuses to save if anything is wrong. Commit via a PR.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from election_watch.media_calls import check

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parents[1]/'public/data'
FILE = PUBLIC/'usa_election_media_calls_v1.json'


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('race_id'); p.add_argument('winner', nargs='?'); p.add_argument('party', nargs='?', choices=['DEM', 'REP', 'IND'])
    p.add_argument('--by', action='append', required=True, help='calling organisation, repeatable (AP, NBC, ...)')
    p.add_argument('--at', required=True, help='call time, ISO with timezone, e.g. 2026-11-04T01:12Z')
    p.add_argument('--url', required=True, help='https link to the call')
    g = p.add_mutually_exclusive_group(); g.add_argument('--runoff', action='store_true'); g.add_argument('--retract', action='store_true')
    a = p.parse_args()
    status = 'runoff' if a.runoff else 'retracted' if a.retract else 'called'
    if status == 'called' and not (a.winner and a.party):
        raise SystemExit('winner and party are required for a call')
    at = a.at.replace('Z', '+00:00')
    entry = {'race_id': a.race_id, 'status': status, 'winner': a.winner if status == 'called' else None,
             'party': a.party if status == 'called' else None, 'called_by': a.by,
             'called_at': datetime.fromisoformat(at).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
             'source_url': a.url, 'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}
    data = json.loads(FILE.read_text())
    data['calls'] = [c for c in data['calls'] if c['race_id'] != a.race_id] + [entry]
    data['calls'].sort(key=lambda c: c['race_id'])
    data['updated_at'] = entry['recorded_at']
    ratings = json.loads((PUBLIC/'usa_election_ratings_review_v1.json').read_text())
    results = json.loads((ROOT/'config/usa_polls/results_2026.json').read_text())
    problems = check(data, ratings, {r.get('race_id'): r for r in results.get('results', [])}, datetime.now(timezone.utc))
    if problems:
        raise SystemExit('not saved: ' + '; '.join(problems))
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print({'saved': a.race_id, 'status': status, 'calls': len(data['calls'])})


if __name__ == '__main__':
    main()
