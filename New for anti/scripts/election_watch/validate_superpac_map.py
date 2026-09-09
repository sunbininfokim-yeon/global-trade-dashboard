#!/usr/bin/env python3
"""Check every published map reference and reconcile money with source snapshots."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from build_superpac import PUBLIC, INDEX
from build_superpac_map import CATALOG, amounts, group_rows


def validate(public, index=None):
    def load(relative):
        path = (public / relative).resolve()
        if not path.is_relative_to(public.resolve()):
            raise ValueError('Asset reference escapes public data')
        return json.loads(path.read_text())
    index = index if index is not None else load(CATALOG)
    counts = {}
    for cycle, meta in index['cycles'].items():
        national = load(meta['national_file'])
        observed, expected = defaultdict(int), defaultdict(int)
        expected_records = 0
        if (public / INDEX).exists():
            fec = load(INDEX).get('cycles', {}).get(cycle)
            if fec:
                for path in fec['state_files'].values():
                    for row in load(path)['spending']:
                        expected_records += row['records']
                        for side in ('support', 'oppose'):
                            expected[row['category'], side] += row[side + '_cents']
        governor = public / 'usa_governor_finance' / cycle / 'WA.json'
        if governor.exists():
            for row in load(str(governor.relative_to(public)))['spending']:
                expected_records += row['records']
                for side in ('support', 'oppose'):
                    expected[row['category'], side] += row[side + '_cents']
        seen, record_count, candidates = set(), 0, 0
        for state_id, state_info in national['states'].items():
            state = load(state_info['data_file'])
            assert state['state_id'] == state_id and state['cycle'] == int(cycle)
            state_rows = []
            for summary in state['races']:
                race = load(summary['data_file'])
                assert race['race_id'] not in seen and race['race_id'] == summary['race_id']
                assert race['cycle'] == int(cycle) and race['state_id'] == state_id
                seen.add(race['race_id'])
                ids, race_rows = set(), []
                for candidate in race['candidates']:
                    assert candidate['candidate_id'] not in ids
                    ids.add(candidate['candidate_id']); candidates += 1
                    candidate_rows = []
                    for phase, section in candidate['election_types'].items():
                        for row in section['allocations']:
                            assert row['candidate_id'] == candidate['candidate_id'] and row['election_type'] == phase
                            assert row['office'] == race['office'] and row['state'] == state_id and row.get('district') == race['district']
                            for side in ('support', 'oppose'):
                                value = row[side + '_cents']
                                assert type(value) is int and abs(value) <= 9007199254740991
                                if row.get('monthly'):
                                    assert sum(m[side + '_cents'] for m in row['monthly'].values()) == value
                                observed[row['category'], side] += value
                            record_count += row['records']
                        assert section['totals_by_category'] == amounts(section['allocations'])
                        candidate_rows.extend(section['allocations'])
                    assert candidate['totals_by_category'] == amounts(candidate_rows)
                    race_rows.extend(candidate_rows)
                assert race['totals_by_category'] == summary['totals_by_category'] == amounts(race_rows)
                assert race['totals_by_election_type'] == {p: amounts(v) for p, v in group_rows(race_rows, 'election_type').items()}
                assert race['totals_by_reported_party'] == {p: amounts(v) for p, v in group_rows(race_rows, 'party').items()}
                state_rows.extend(race_rows)
            for office, totals in state_info['totals_by_office'].items():
                assert totals == amounts([r for r in state_rows if r['office'] == office])
        assert dict(observed) == dict(expected), f'{cycle}: source/map money mismatch'
        assert record_count == expected_records, f'{cycle}: duplicated/missing source rows'
        counts[cycle] = {'races': len(seen), 'candidate_race_records': candidates, 'source_records': record_count}
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, default=PUBLIC)
    args = parser.parse_args()
    print(json.dumps(validate(args.public)))
