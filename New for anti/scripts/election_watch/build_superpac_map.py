#!/usr/bin/env python3
"""Build a static, versioned national -> state -> race contract for the map UI."""
from collections import defaultdict
import argparse
import hashlib
import json
from pathlib import Path
from build_superpac import PUBLIC, ROOT, INDEX, atomic_json
from election_watch.superpac import STATES, now
from election_watch.superpac_schedule import reporting_cycle
from election_watch.districts import normalize_house, district_code, district_audit

CATALOG = 'usa_election_finance_index_v1.json'
CATEGORIES = ['super_pac', 'hybrid_pac', 'single_candidate_ie', 'other_independent_spender', 'unclassified', 'state_independent_expenditure_committee', 'state_independent_spender_unclassified']
OFFICES = {'H': 'house', 'S': 'senate', 'P': 'president', 'G': 'governor'}


def read(path):
    return json.loads(path.read_text())


def immutable(public, prefix, payload):
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    path = f'usa_election_finance/{prefix}-{digest}.json'
    if not (public / path).exists():
        atomic_json(public / path, payload)
    return path


def amounts(rows):
    result = {}
    for category in sorted(set(CATEGORIES + [r['category'] for r in rows])):
        selected = [r for r in rows if r['category'] == category]
        result[category] = {'support_cents': sum(r['support_cents'] for r in selected) if selected else None,
                            'oppose_cents': sum(r['oppose_cents'] for r in selected) if selected else None,
                            'records': sum(r['records'] for r in selected),
                            'status': 'observed_partial' if selected else 'no_observed_records'}
    return result


def race_key(state, office, district=None):
    return f'USA:{state}:{office}' + (f':{district}' if office == 'house' else '')


def group_rows(rows, field):
    groups = defaultdict(list)
    for row in rows:
        groups[row.get(field) or 'UNKNOWN'].append(row)
    return dict(sorted(groups.items()))


def candidate_cards(rows, roster):
    output = []
    by_id = group_rows(rows, 'candidate_id')
    registrations = group_rows(roster, 'candidate_id')
    for candidate_id in sorted(set(by_id) | set(registrations)):
        spending, entries = by_id.get(candidate_id, []), registrations.get(candidate_id, [])
        names = sorted({r.get('candidate_name') or r.get('name') or candidate_id for r in spending + entries})
        phases = {}
        for phase, selected in group_rows(spending, 'election_type').items():
            # Preserve report party and committee categories rather than guessing a party switch date.
            phases[phase] = {'totals_by_category': amounts(selected), 'allocations': selected}
        output.append({'candidate_id': candidate_id, 'name': entries[0].get('name', names[0]) if entries else names[0],
            'reported_names': names, 'reported_parties': sorted({r.get('party') or 'UNKNOWN' for r in spending + entries}),
            'registration_records': entries, 'registration_status': entries[0].get('registration_status', 'fec_registered_ballot_unverified') if entries else 'spending_only_roster_unverified',
            'totals_by_category': amounts(spending), 'election_types': phases})
    return output


def geometry_catalog(public):
    result = {}
    for path in sorted((public / 'congressional_districts' / 'USA').glob('*.json')):
        geo = read(path)
        for feature in geo.get('features', []):
            props = feature.get('properties') or {}
            state, raw = props.get('state_id'), props.get('district')
            district = str(raw).zfill(2) if raw is not None else None
            if state and district:
                result[(state, district)] = {'asset': str(path.relative_to(public)), 'source': geo.get('source'), 'retrieved': geo.get('retrieved')}
    return result


def build(public=PUBLIC, cadence='daily'):
    federal = read(public / INDEX) if (public / INDEX).exists() else {'cycles': {}}
    governor_sources = defaultdict(dict)
    for path in sorted((public / 'usa_governor_finance').glob('*/*.json')):
        source = read(path)
        if source.get('schema') != 'usa_governor_source_v1' or source.get('state') not in STATES or path.stem != source.get('state') or path.parent.name != str(source.get('cycle')):
            raise ValueError('Invalid governor source contract')
        governor_sources[str(source['cycle'])][source['state']] = source
    geometry = geometry_catalog(public)
    source_directory = read(ROOT / 'config/usa_state_campaign_finance_sources_v1.json')
    catalog = {'schema': 'usa_election_finance_index_v1', 'generated_at': now(), 'currency': 'USD', 'amount_unit': 'cents',
        'pipeline_role': 'ui_read_model', 'upstream_index': INDEX,
        'measure': 'independent_expenditure_for_or_against_candidate',
        'measure_label_ko': '후보 대상 외부 독립지출 (캠프가 받은 후원금 아님)',
        'cycles': {}, 'categories': CATEGORIES, 'governor_source_directory': source_directory,
        'display_contract': {'federal_superpac_categories': ['super_pac'],
            'governor_independent_expenditure_categories': ['state_independent_expenditure_committee', 'state_independent_spender_unclassified'],
            'governor_label_ko': '주 공시 독립지출 (슈퍼팩 유형 미확인)'},
        'join_contract': {'state': 'feature.properties.state_id', 'district': 'String(feature.properties.district).padStart(2, "0")',
            'race_id': 'USA:{state_id}:house:{district}', 'boundary_election_match_verified': False},
        'rules_ko': ['null은 미확보/관측 없음이며 0으로 바꾸지 마세요. 금액은 정수 센트입니다.',
            'super_pac만 슈퍼팩 필터에 포함하고 주 미분류 독립지출은 별도 표시하세요.',
            '경선·본선은 election_types의 원문 코드로 필터링하세요. 등록 명부에 경선 참여를 추정하지 마세요.',
            '대통령은 US 전국 단위. 상원·주지사는 주 전체 단위이며 하원 구역에 배분하지 마세요.',
            '지도는 기존 경계와 신고 선거구 코드만 연결합니다. 해당 선거의 경계 일치 여부는 미검증입니다.']}
    for cycle in sorted(set(federal.get('cycles', {})) | set(governor_sources)):
        meta = federal.get('cycles', {}).get(cycle)
        state_sources = governor_sources.get(cycle, {})
        rows, roster = [], []
        if meta:
            for path in meta['state_files'].values():
                shard = read(public / path)
                if shard['cycle'] != int(cycle):
                    raise ValueError('FEC shard cycle mismatch')
                rows.extend(shard['spending']); roster.extend(shard['candidates'])
        for state, source in state_sources.items():
            if any(r['state'] == state and r['office'] == 'governor' for r in rows):
                raise ValueError('Automated and manual governor sources overlap')
            if any(r['state'] != state or r['office'] != 'governor' or r['cycle'] != int(cycle) for r in source['spending']):
                raise ValueError('Governor row scope mismatch')
            if any(c['state'] != state or c['office'] != 'G' or c['election_year'] != int(cycle) for c in source.get('candidates', [])):
                raise ValueError('Governor roster scope mismatch')
            rows.extend(source['spending'])
            roster.extend(source.get('candidates', []))
        rows, roster = normalize_house(rows, roster, geometry, cycle)
        audit = district_audit(rows, roster)
        records_by_race, roster_by_race = defaultdict(list), defaultdict(list)
        for r in rows:
            key = (r['state'], r['office'], r.get('district'))
            if r['office'] not in ('house', 'senate', 'president', 'governor'):
                raise ValueError('Unsupported office')
            records_by_race[key].append(r)
        for c in roster:
            office = OFFICES[c['office']]
            state = 'US' if office == 'president' else c['state']
            district = district_code(c.get('district')) if office == 'house' else None
            roster_by_race[(state, office, district)].append(c)
        keys = set(records_by_race) | set(roster_by_race) | {(s, 'house', d) for s, d in geometry}
        keys |= {(s, office, None) for s in STATES for office in ('senate', 'governor')}
        keys.add(('US', 'president', None))
        state_races = defaultdict(list)
        source_status = {'federal': {'status': meta['status'] if meta else 'not_collected', 'last_success_at': meta['generated_at'] if meta else None,
            'last_filing_date': meta.get('coverage', {}).get('last_filing_date') if meta else None,
            'quality': meta.get('quality') if meta else None, 'notices_included': False}}
        for state, source in state_sources.items():
            source_status[state + '_governor'] = {'status': source['status'], 'last_success_at': source['generated_at'],
                'last_filing_date': source['last_filing_date'], 'quality': source['quality'],
                'source_data_updated_at': source.get('source_data_updated_at'),
                'reviewed_filer_registry_as_of': source.get('reviewed_filer_registry_as_of'),
                'amount_basis': source.get('amount_basis'), 'limitations_ko': source.get('limitations_ko', [])}
        for source in source_status.values():
            current = int(cycle) == reporting_cycle()
            previous = int(cycle) == reporting_cycle() - 2
            source['refresh_policy'] = cadence if current else 'monthly' if previous else 'manual_archive'
            source['expected_interval_hours'] = (168 if cadence == 'weekly' else 24) if current else 744 if previous else None
            source['stale_after_hours'] = (240 if cadence == 'weekly' else 72) if current else 1080 if previous else None
        for state, office, district in sorted(keys, key=lambda k: (k[0], k[1], k[2] or '')):
            selected = records_by_race.get((state, office, district), [])
            registered = roster_by_race.get((state, office, district), [])
            if office == 'governor':
                coverage = (meta or {}).get('coverage', {}).get('governor', {}).get(state, {'status': 'unsupported'})
                source = state_sources.get(state)
                status = source['status'] if source else coverage['status']
                source_key = state + '_governor' if source else 'manual_governor' if selected else None
            else:
                status, source_key = (meta['status'], 'federal') if meta else ('not_collected', 'federal')
            geo = geometry.get((state, district)) if office == 'house' else None
            join = {'state_id': state, 'district': district, 'existing_geometry_found': bool(geo),
                'geometry_asset': geo['asset'] if geo else None, 'geometry_source': geo.get('source') if geo else None,
                'boundary_election_match_verified': False, 'scope': 'district' if office == 'house' else 'national' if office == 'president' else 'statewide'}
            race_id = race_key(state, office, district)
            payload = {'schema': 'usa_election_finance_race_v1', 'cycle': int(cycle), 'race_id': race_id,
                'state_id': state, 'office': office, 'district': district, 'map_join': join,
                'district_source': sorted({r['district_source']['status'] for r in selected + registered if r.get('district_source')}),
                'status': status, 'source_status_key': source_key, 'currency': 'USD',
                'coverage_note_ko': ('연결된 주 공시 양식의 부분 집계입니다.' if source_key else '주 공시 수집기 미연결. 관측 없음 또는 실제 지출 0을 뜻하지 않습니다.') if office == 'governor' else None, 'amount_unit': 'cents',
                'source_limitations_ko': source.get('limitations_ko', []) if office == 'governor' and source else [],
                'amount_basis': source.get('amount_basis') if office == 'governor' and source else None,
                'seat_class': None, 'ballot_election_id': None,
                'totals_by_category': amounts(selected),
                'totals_by_election_type': {p: amounts(v) for p, v in group_rows(selected, 'election_type').items()},
                'totals_by_reported_party': {p: amounts(v) for p, v in group_rows(selected, 'party').items()},
                'candidates': candidate_cards(selected, registered)}
            path = immutable(public, f'{cycle}/races/{state}-{office}' + (f'-{district}' if district is not None else ''), payload)
            state_races[state].append({'race_id': race_id, 'office': office, 'district': district, 'status': status,
                'candidate_count': len(payload['candidates']), 'map_join': join, 'totals_by_category': payload['totals_by_category'], 'data_file': path})
        states = {}
        for state, races in sorted(state_races.items()):
            payload = {'schema': 'usa_election_finance_state_v1', 'cycle': int(cycle), 'state_id': state, 'races': races}
            path = immutable(public, f'{cycle}/states/{state}', payload)
            states[state] = {'state_id': state, 'data_file': path, 'race_count': len(races),
                'governor_status': next((r['status'] for r in races if r['office'] == 'governor'), 'not_applicable'),
                'totals_by_office': {office: amounts([r for r in rows if r['state'] == state and r['office'] == office])
                    for office in sorted({r['office'] for r in races})}}
        catalog['cycles'][cycle] = {'states': states, 'source_status': source_status,
            'sources': (meta.get('sources', []) if meta else []) + [{'url': v['source_url'], 'metadata_url': v['metadata_url']} for v in state_sources.values()],
            'limitations_ko': (meta.get('limitations_ko', []) if meta else ['연방 자료 미수집']) + [note for v in state_sources.values() for note in v['limitations_ko']],
            'unmatched_district_race_ids': [race_key(s, o, d) for s, o, d in keys if o == 'house' and (s, d) not in geometry]}
        catalog['cycles'][cycle]['unmatched_district_race_ids'].sort()
        national = {'schema': 'usa_election_finance_national_v1', 'cycle': int(cycle),
            'states': catalog['cycles'][cycle].pop('states'),
            'district_audit': audit,
            'unmatched_district_race_ids': catalog['cycles'][cycle].pop('unmatched_district_race_ids')}
        catalog['cycles'][cycle]['national_file'] = immutable(public, f'{cycle}/national', national)
    # The map catalog is the sole commit point for all immutable map files.
    from validate_superpac_map import validate
    validate(public, catalog)
    atomic_json(public / CATALOG, catalog)
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, default=PUBLIC)
    args = parser.parse_args()
    result = build(args.public)
    print(json.dumps({'cycles': list(result['cycles']), 'catalog': CATALOG}))
