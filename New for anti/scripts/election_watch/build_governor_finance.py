#!/usr/bin/env python3
"""Collect implemented state sources without requiring a federal API key."""
import argparse
import json
from pathlib import Path
from build_superpac import PUBLIC, ROOT, atomic_json
from election_watch.governor_wa import collect as collect_wa
from election_watch.governor_ca import collect as collect_ca
from election_watch.governor_tx import collect as collect_tx
from election_watch.governor_ny import collect as collect_ny
from election_watch.superpac import SourceError, now
from election_watch.governor_matchups import validate_snapshot
from election_watch.superpac_schedule import reporting_cycle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycle', type=int, default=reporting_cycle())
    parser.add_argument('--state', choices=['WA','CA','TX','NY'], default='WA')
    parser.add_argument('--ca-local-tables', type=Path, help='Reviewed local official tables; offline verification only')
    parser.add_argument('--tx-local-archive', type=Path, help='Official TEC ZIP; offline verification only')
    parser.add_argument('--public', type=Path, default=PUBLIC)
    args = parser.parse_args()
    if args.cycle < 2010 or args.cycle % 2:
        parser.error('even reporting cycle >= 2010 required')
    try:
        roster_path = ROOT / 'config/governor_candidates' / str(args.cycle) / (args.state + '.json')
        roster = json.loads(roster_path.read_text())['candidates'] if roster_path.exists() else []
        matchups_path = ROOT / 'config/governor_matchups' / (str(args.cycle) + '.json')
        snapshot = json.loads(matchups_path.read_text()) if matchups_path.exists() else None
        if snapshot:
            validate_snapshot(snapshot, args.cycle, now()[:10])
        matchup = snapshot['contests'].get(args.state) if snapshot else None
        if matchup and matchup['status'] == 'reported_general_matchup':
            by_id = {c['candidate_id']: c for c in roster}
            for nominee in matchup['candidates']:
                if nominee['candidate_id'] in by_id:
                    # Keep the state-certified identity and its primary source;
                    # a secondary general roster may supply reviewed aliases.
                    candidate = by_id[nominee['candidate_id']]
                    candidate['reported_name_aliases'] = sorted(set(candidate.get('reported_name_aliases', []))
                        | set(nominee.get('reported_name_aliases', [])) | {nominee['name']})
                else:
                    by_id[nominee['candidate_id']] = nominee
            roster = list(by_id.values())
        if args.state == 'WA':
            payload = collect_wa(args.cycle)
        elif args.state == 'CA':
            ballot_dates = {matchup['primary_date']: 'P' + str(args.cycle), matchup['election_date']: 'G' + str(args.cycle)} if matchup else None
            payload = collect_ca(args.cycle, roster, args.ca_local_tables, ballot_dates=ballot_dates)
        elif args.state == 'NY':
            registry_path = ROOT / 'config/governor_ie_filers' / str(args.cycle) / 'NY.json'
            if not registry_path.exists():
                raise SourceError('New York reviewed IE filer registry unavailable for this cycle')
            payload = collect_ny(args.cycle, roster, json.loads(registry_path.read_text()))
        else:
            payload = collect_tx(args.cycle, args.tx_local_archive, roster)
        if payload.get('schema') != 'usa_governor_source_v1':
            raise SourceError('Governor source is audit only; support/oppose verification required; old snapshot preserved')
        atomic_json(args.public / 'usa_governor_finance' / str(args.cycle) / (args.state + '.json'), payload)
        print(json.dumps({'cycle': args.cycle, 'state': args.state, 'quality': payload['quality']}))
    except (SourceError, OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc))
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
