"""Requested regions and reviewed company address points, without inferred polls."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
import math
import re
from urllib.parse import urlparse
from .polls import digest, read, require

BOUNDARY_TOLERANCE_DEGREES = .001  # Census addresses are interpolated, not roof points.
EPA_FRS_QUERY = '/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/FRS_INTERESTS/FeatureServer/0/query'


def reviewed_coordinate_source(url):
    parsed = urlparse(url)
    return (parsed.scheme == 'https' and not parsed.username and not parsed.password
            and ((parsed.hostname == 'records.tceq.texas.gov' and parsed.path == '/cs/idcplg')
                 or (parsed.hostname == 'services.arcgis.com' and parsed.path == EPA_FRS_QUERY)))


def segment_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((point[0]-a[0])*dx + (point[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return math.hypot(point[0]-a[0]-t*dx, point[1]-a[1]-t*dy)


def ring_location(point, ring, tolerance=BOUNDARY_TOLERANCE_DEGREES):
    require(len(ring) >= 4 and ring[0] == ring[-1], 'invalid polygon ring')
    inside = False
    x, y = point
    for a, b in zip(ring, ring[1:]):
        if segment_distance(point, a, b) <= tolerance:
            return 'boundary'
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return 'inside' if inside else 'outside'


def geometry_location(point, geometry, tolerance=BOUNDARY_TOLERANCE_DEGREES):
    kind = geometry['type']
    require(kind in ('Polygon', 'MultiPolygon'), 'unsupported district geometry')
    polygons = [geometry['coordinates']] if kind == 'Polygon' else geometry['coordinates']
    locations = []
    for rings in polygons:
        outer = ring_location(point, rings[0], tolerance)
        if outer != 'inside':
            locations.append(outer)
            continue
        holes = [ring_location(point, ring, tolerance) for ring in rings[1:]]
        locations.append('boundary' if 'boundary' in holes else 'outside' if 'inside' in holes else 'inside')
    return 'boundary' if 'boundary' in locations else 'inside' if 'inside' in locations else 'outside'


def match_site(site, geometry_root, congress, as_of):
    """Re-evaluate coordinates when district files change; never trust a stored CD."""
    output = deepcopy(site)
    output.update(district=None, house_race_id=None, mapping_status='hold')
    try:
        require(urlparse(site['address_source_url']).scheme == 'https', 'invalid_address_source')
        require(date.fromisoformat(site['address_reviewed_on']) <= date.fromisoformat(as_of), 'future_address_review')
        geo = site['geocoding']
        coordinate_review = site.get('coordinate_review')
        if geo['status'] != 'matched' and coordinate_review:
            geo = coordinate_review
            require(reviewed_coordinate_source(geo['source_url']), 'unverified_facility_coordinate_source')
            require(geo['source_role'] in ('government_facility_filing', 'government_facility_registry') and geo['legal_entity']
                    and geo['record_id'] and geo['coordinate_method'], 'incomplete_coordinate_review')
            require(date.fromisoformat(geo['reviewed_on']) <= date.fromisoformat(as_of), 'future_coordinate_review')
        else:
            require(geo['status'] == 'matched', geo.get('reason', 'address_not_geocoded'))
            require(urlparse(geo['request_url']).hostname == 'geocoding.geo.census.gov', 'unverified_coordinate_source')
            require(date.fromisoformat(geo['retrieved_on']) <= date.fromisoformat(as_of), 'future_geocode')
        require(geo['input_address_sha256'] == digest(site['address']), 'address_changed')
        require(geo['matched_state'] == site['state'], 'geocoder_state_mismatch')
        points = [geo['coordinates']] + geo.get('alternative_coordinates', [])
        for point in points:
            require(len(point) == 2 and all(type(v) in (int, float) and math.isfinite(v) for v in point)
                    and -180 <= point[0] <= 180 and -90 <= point[1] <= 90, 'invalid_coordinates')
        geometry = read(geometry_root/f'{site["state"]}.json')
        require(geometry['type'] == 'FeatureCollection'
                and f'{congress}th Congressional Districts' in geometry['source'], 'boundary_congress_mismatch')
        require(date.fromisoformat(geometry['retrieved']) <= date.fromisoformat(as_of), 'future_boundary')
        # 60 km/degree is conservative for longitude in these lower-48 sites.
        # A review buffer is uncertainty policy, not a reported accuracy claim.
        buffers = [geo.get('accuracy_m') or 0, geo.get('uncertainty_buffer_m') or 0]
        require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in buffers), 'invalid_coordinate_accuracy')
        tolerance = max(BOUNDARY_TOLERANCE_DEGREES, max(buffers)/60000)
        districts = []
        for point in points:
            matches, boundary = [], False
            for feature in geometry['features']:
                require(feature['properties']['state_id'] == site['state'], 'boundary_state_mismatch')
                location = geometry_location(point, feature['geometry'], tolerance)
                if location == 'boundary':
                    boundary = True
                elif location == 'inside':
                    matches.append(str(feature['properties']['district']).zfill(2))
            require(not boundary, 'near_district_boundary')
            require(len(matches) == 1, 'ambiguous_or_missing_district')
            require(re.fullmatch(r'\d{2}', matches[0]) is not None, 'invalid_district')
            districts.append(matches[0])
        require(len(set(districts)) == 1, 'facility_coordinate_district_disagreement')
        output.update(district=districts[0], house_race_id=f'USA:{site["state"]}:house:{districts[0]}',
                      mapping_status='address_point_mapped', mapping_reason=None,
                      boundary={'congress': congress, 'source': geometry['source'],
                                'retrieved_on': geometry['retrieved'], 'sha256': digest(geometry),
                                'boundary_tolerance_degrees': tolerance},
                      coordinate_source_used='reviewed_government_filing' if geo is coordinate_review else 'census_address_range',
                      mapping_limitations_ko='Census 주소 구간 보간 또는 검토한 정부 시설 좌표를 현행 선거구 경계에 대조. 사업장 전체 부지·노동자 거주지·정치적 영향은 판정하지 않습니다.')
    except (ValueError, KeyError, TypeError, OSError) as exc:
        output['mapping_reason'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    return output


def apply_priorities(policy, config, geometry_root, as_of):
    require(config.get('schema') == 'usa_poll_priorities_v1' and config.get('cycle') == policy['cycle'],
            'priority schema/cycle')
    require(date.fromisoformat(config['reviewed_on']) <= date.fromisoformat(as_of), 'future_priority_review')
    require(config['priority_order'] == ['requested_states', 'cook_toss_up_and_lean', 'korean_company_facilities'],
            'priority order changed')
    selected = deepcopy(policy)
    require(len(config['requested_states']) == len(set(config['requested_states'])), 'duplicate requested state')
    sites, seen = [], set()
    congress = (policy['cycle']-1788)//2 + 1
    for site in config['company_sites']:
        require(site['id'] not in seen and re.fullmatch(r'[A-Z]{2}', site['state']), 'invalid company site ID/state')
        seen.add(site['id'])
        mapped = match_site(site, geometry_root, congress, as_of)
        sites.append(mapped)
        rid = mapped['house_race_id']
        if not rid:
            continue
        if rid not in selected['races']:
            selected['races'][rid] = {
                'state': mapped['state'], 'office': 'house', 'district': mapped['district'],
                'subject': f'{policy["cycle"]} {mapped["state"]}-{mapped["district"]}',
                'poll_type': 'us-representative', 'seat_name': None,
                'contest_id': f'{rid}:{policy["cycle"]}:general',
                'general_from': f'{policy["cycle"]}-09-01', 'election_date': f'{policy["cycle"]}-11-03',
                'schedule_status': 'watch_slot_unverified', 'required_candidates': [], 'candidates': {},
                'selection_reason_ko': '한국기업 주소의 하원 선거구. 후보·조사는 별도 원문 검토 전까지 보류.'}
        selected['races'][rid].setdefault('company_site_ids', []).append(site['id'])
        # Statewide joins only for already reviewed 2026 election slots.
        for office in ('senate', 'governor'):
            statewide = selected['races'].get(f'USA:{mapped["state"]}:{office}')
            if statewide:
                statewide.setdefault('company_site_ids', []).append(site['id'])
    for rid, race in selected['races'].items():
        reasons = []
        if race['state'] in config['requested_states']:
            reasons.append('requested_state')
        if race.get('monitor_priority'):
            reasons.append('cook_toss_up_and_lean')
        if race.get('company_site_ids'):
            reasons.append('korean_company_facility')
        order = min(({'requested_state': 1, 'cook_toss_up_and_lean': 2,
                      'korean_company_facility': 3}[reason] for reason in reasons), default=4)
        race['collection_priority'] = {'order': order, 'reasons': reasons or ['existing_target']}
    selected['states'] = sorted(set(selected['states']) | {r['state'] for r in selected['races'].values()})
    selected['priority_regions'] = {'reviewed_on': config['reviewed_on'], 'requested_states': config['requested_states'],
                                    'order': config['priority_order']}
    selected['company_interest'] = {'scope_ko': config['company_scope_ko'], 'sites': sites,
                                    'mapped_site_count': sum(s['mapping_status'] == 'address_point_mapped' for s in sites),
                                    'held_site_count': sum(s['mapping_status'] == 'hold' for s in sites)}
    return selected


def load_finance_links(index_path, cycle):
    root = index_path.parent.resolve()
    index = read(index_path)
    require(index['schema'] == 'usa_election_finance_index_v1', 'finance index schema')
    def asset(path):
        target = (root/path).resolve()
        require(target.is_relative_to(root) and target.suffix == '.json', 'invalid finance asset path')
        return read(target)
    national_file = index['cycles'][str(cycle)]['national_file']
    national = asset(national_file)
    require(national['cycle'] == cycle and national['schema'] == 'usa_election_finance_national_v1', 'finance cycle/schema')
    races = {}
    for state, entry in national['states'].items():
        data = asset(entry['data_file'])
        require(data['cycle'] == cycle and data['state_id'] == state, 'finance state mismatch')
        for race in data['races']:
            rid = race['race_id']
            require(rid.startswith(f'USA:{state}:') and rid not in races, 'invalid finance race ID')
            payload = asset(race['data_file'])
            require(payload['schema'] == 'usa_election_finance_race_v1' and payload['cycle'] == cycle
                    and payload['race_id'] == rid and payload['status'] == race['status'], 'finance race mismatch')
            races[rid] = {'data_file': race['data_file'], 'status': race['status'],
                          'totals_by_category': payload.get('totals_by_category', {}),
                          'totals_by_election_type': payload.get('totals_by_election_type', {})}
    return {'races': races, 'status': 'loaded', 'generated_at': index['generated_at'], 'national_file': national_file}


def attach_coverage(board, raw_rows, policy, finance_board):
    """Publish empty-race reasons too; lack of provider rows is not proof of no poll."""
    provider = Counter((r.get('subject'), r.get('poll_type')) for r in raw_rows)
    rejected = defaultdict(list)
    for row in board['review_queue']:
        rejected[row['race_id']].append(row)
    finance = (finance_board or {}).get('races', {})
    race_coverage = {}
    for rid, race in board['races'].items():
        eligible = [p for p in race['observations'] if p['aggregation_eligibility']['eligible']]
        count = provider[(race['subject'], race['poll_type'])]
        windows = race['windows']
        status = ('election_closed' if race['phase'] != 'pre_election' else
                  'recent_7d' if windows['7']['pollster_count'] else
                  'recent_14d_only' if windows['14']['pollster_count'] else
                  'older_polls_only' if eligible else
                  'reference_only' if race['observations'] else
                  'review_required' if count else 'no_provider_record')
        missing = sorted(rejected[rid], key=lambda x: (x.get('field_end') or '', x.get('id') or ''), reverse=True)
        race_coverage[rid] = {'priority': race.get('collection_priority', {'order': 4, 'reasons': ['existing_target']}),
            'status': status, 'provider_record_count': count, 'accepted_count': len(race['observations']),
            **({'reviewed_primary_supplement_count': sum('primary_source_capture' in p for p in race['observations'])}
               if any('primary_source_capture' in p for p in race['observations']) else {}),
            'aggregation_eligible_count': len(eligible), 'reference_only_count': len(race['observations'])-len(eligible),
            'matchup_reviewed': len(race['required_candidates']) >= 2,
            'latest_accepted_field_end': max((p['field_end'] for p in race['observations']), default=None),
            'windows': {days: {'status': windows[days]['status'], 'pollster_count': windows[days]['pollster_count']}
                        for days in ('7', '14')},
            'rejection_reasons': dict(Counter(p['reason'] for p in missing)),
            'review_queue_ids': [p['id'] for p in missing],
            'finance_join': {'race_id': rid, 'file': finance.get(rid, {}).get('data_file'),
                             'status': finance.get(rid, {}).get('status', 'not_in_loaded_finance_board'),
                             'finance_generated_at': (finance_board or {}).get('generated_at'),
                             'measure': 'candidate_targeted_independent_expenditure'}}
    groups = {}
    for group, reason in [('requested_states', 'requested_state'), ('cook_toss_up_and_lean', 'cook_toss_up_and_lean'),
                          ('korean_company_facilities', 'korean_company_facility')]:
        members = [rid for rid, item in race_coverage.items() if reason in item['priority']['reasons']]
        groups[group] = {'race_count': len(members), 'with_observations': sum(race_coverage[r]['accepted_count'] > 0 for r in members),
            'recent_7d': sum(race_coverage[r]['windows']['7']['pollster_count'] > 0 for r in members),
            'recent_14d': sum(race_coverage[r]['windows']['14']['pollster_count'] > 0 for r in members)}
    board['monitoring'] = {'priority_regions': policy.get('priority_regions'), 'groups': groups,
        'finance_links_status': (finance_board or {}).get('status', 'not_loaded'),
        'race_coverage': dict(sorted(race_coverage.items(), key=lambda x: (x[1]['priority']['order'], x[0]))),
        'limitations_ko': 'Cook은 수동 검토한 감시 순위. 빈 지역은 수집 API의 미발견·대진 미검증·출처 보류·기간 초과를 구분하며 조사 자체의 부재로 단정하지 않습니다. 그룹 간 중복 포함.'}
    company = deepcopy(policy.get('company_interest'))
    if company:
        for site in company['sites']:
            rid = site['house_race_id']
            statewide = [f'USA:{site["state"]}:{office}' for office in ('senate', 'governor')]
            # Finance can be joined even when the company address is held; only
            # statewide offices in a held site's reviewed state are then linked.
            joined = [r for r in ([rid] if rid else [])+statewide if r in board['races'] or r in finance]
            site['race_joins'] = [{'race_id': r, 'polls_monitored': r in board['races'],
                                  'finance_asset_available': r in finance,
                                  'finance_status': finance.get(r, {}).get('status'),
                                  'finance_file': finance.get(r, {}).get('data_file'),
                                  'poll_coverage_status': race_coverage[r]['status'] if r in race_coverage else 'not_monitored'}
                                 for r in joined]
        board['company_interest'] = company
    return board
