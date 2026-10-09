"""Source-bounded governor ballot identities; spending coverage stays independent."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
from html import unescape
import re
from urllib.request import Request, urlopen

from .superpac import SourceError, STATES

URL = 'https://www.nga.org/governors/elections/'
PARTIES = {'D': 'DEM', 'R': 'REP', 'I': 'IND', 'Independent': 'IND', 'L': 'LIB', 'G': 'GRE'}
ROSTER_PARTIES = set(PARTIES.values()) | {'UC', 'WRI', 'CST', 'OTH', 'APV'}


def text(value):
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', value)).split())


def name_key(value):
    # Full names only. A nickname or missing middle initial is never guessed.
    return ' '.join(sorted(re.sub(r'[^a-z0-9 ]', ' ', value.casefold()).split()))


def parse(html, cycle, expected_states, as_of, registries=None):
    """Read only year-linked state map panels, excluding old results/territories.

    Missing or placeholder nominees hold that state; a changed page/universe
    fails the whole collection so the previous reviewed snapshot is preserved.
    """
    expected = set(expected_states)
    if not expected or not expected <= set(STATES):
        raise SourceError('Governor roster state universe unavailable')
    found = {}
    registries = registries or {}
    for match in re.finditer(r'<div\b[^>]*data-original-id="US-([A-Z]{2})"[^>]*>(.*?)</div>', html, re.S):
        state, body = match.groups()
        heading = re.search(r'<h3\b[^>]*>(.*?)</h3>', body, re.S)
        if not heading or f'gubernatorial_election,_{cycle}' not in heading.group(1) or state not in expected:
            continue
        if state in found:
            raise SourceError('Duplicate governor state panel')
        state_name = text(heading.group(1)).replace('🡭', '').strip()
        primary = re.search(r'Primary Date:\s*([A-Za-z]+ \d{1,2}, \d{4})', text(body))
        if not primary:
            raise SourceError('Governor primary date missing or changed')
        primary_date = datetime.strptime(primary.group(1), '%B %d, %Y').date().isoformat()
        if int(primary_date[:4]) != cycle:
            raise SourceError('Governor primary year mismatch')
        listing = re.search(r'General Election Candidates.*?<ul\b[^>]*>(.*?)</ul>', body, re.S)
        nominees, held = [], None
        if not listing:
            held = 'source_has_no_complete_general_candidate_section'
        else:
            for item in re.findall(r'<li\b[^>]*>(.*?)</li>', listing.group(1), re.S):
                item = text(item)
                name = re.fullmatch(r'(?:Gov\.\s+)?(.+?)\s*\((D|R|I|Independent|L|G)\)', item)
                if not name or re.search(r'runoff|winner|primary|pending|TBD', name.group(1), re.I):
                    held = 'source_contains_placeholder_or_unparsed_candidate'
                    break
                display, party = name.group(1), PARTIES[name.group(2)]
                candidates = [c for c in registries.get(state, [])
                    if c['party'] == party and any(name_key(a) == name_key(display)
                        for a in [c['name'], *c.get('reported_name_aliases', [])])]
                if len({c['candidate_id'] for c in candidates}) > 1:
                    raise SourceError('Ambiguous governor registry identity')
                candidate_id = candidates[0]['candidate_id'] if candidates else (
                    f'{state}:reported-general:{cycle}:' + hashlib.sha256(name_key(display).encode()).hexdigest()[:16])
                aliases = sorted({display, *(candidates[0].get('reported_name_aliases', []) if candidates else [])})
                nominees.append({'candidate_id': candidate_id, 'name': display,
                    'reported_name_aliases': aliases, 'party': party, 'office': 'G', 'state': state,
                    'district': None, 'election_year': cycle,
                    'registration_status': 'reported_general_ballot_not_state_certification',
                    'ballot_election_date': f'{cycle}-11-03', 'source_url': URL,
                    'candidate_identity_basis': 'NGA_general_candidate_section_full_name_party_office_cycle'})
            if len(nominees) < 2:
                held = held or 'source_has_fewer_than_two_candidates'
            if len({name_key(c['name']) for c in nominees}) != len(nominees):
                raise SourceError('Duplicate governor candidate name')
        found[state] = {'state': state, 'state_name': state_name, 'primary_date': primary_date,
            'election_date': f'{cycle}-11-03', 'source_url': URL,
            'status': 'review_required' if held else 'reported_general_matchup',
            'hold_reason': held, 'candidates': [] if held else nominees}
    if set(found) != expected:
        raise SourceError('Governor roster universe changed; previous snapshot preserved')
    return {'schema': 'usa_governor_matchups_v1', 'cycle': cycle, 'reviewed_on': as_of,
        'source_url': URL, 'source_sha256': hashlib.sha256(html.encode()).hexdigest(),
        'scope': '50_states_only_reviewed_contest_universe', 'contests': dict(sorted(found.items())),
        'coverage': {'contest_count': len(found),
            'reviewed_matchup_count': sum(r['status'] == 'reported_general_matchup' for r in found.values()),
            'held_states': sorted(s for s, r in found.items() if r['status'] != 'reported_general_matchup')},
        'limitations_ko': ['NGA에 명시된 본선 대진이며 주 선거관리기관의 인증 명부 전체를 뜻하지 않습니다. 제3당·기입 후보 누락 가능.',
            '후보 명부와 외부 독립지출 수집 범위는 별개입니다. 명부가 있어도 지출 미확보를 0으로 바꾸지 않습니다.',
            '대진 표가 없거나 결선 승자 자리표시자가 남은 주는 검토 대기로 유지합니다. 이전 회기 결과·미국령은 제외합니다.']}


def collect(cycle, expected_states, as_of, registries=None):
    with urlopen(Request(URL, headers={'User-Agent': 'ElectionWatch/1.0'}), timeout=30) as response:
        if not response.url.startswith(URL):
            raise SourceError('Unexpected NGA redirect')
        raw = response.read(3_000_001)
    if len(raw) > 3_000_000:
        raise SourceError('NGA response exceeds budget')
    return parse(raw.decode('utf-8'), cycle, expected_states, as_of, registries)


def apply_ballot_reviews(snapshot, reviews, as_of):
    """Use explicitly reviewed state-agency listings where the NGA page is held.

    These are reviewed snapshots, not newly installed statewide API adapters.
    Source URLs and ballot scope remain attached to each contest/candidate.
    """
    if (reviews.get('schema') != 'usa_governor_ballot_reviews_v1'
            or reviews['cycle'] != snapshot['cycle']
            or date.fromisoformat(reviews['reviewed_on']) > date.fromisoformat(as_of)):
        raise SourceError('Governor ballot review schema/cycle/date mismatch')
    selected = deepcopy(snapshot)
    sources = deepcopy(selected.get('additional_sources', []))
    for state, review in reviews['contests'].items():
        if state not in selected['contests']:
            raise SourceError('Ballot review outside governor contest universe')
        contest = selected['contests'][state]
        if date.fromisoformat(review.get('reviewed_on', reviews['reviewed_on'])) > date.fromisoformat(as_of):
            raise SourceError('Future governor ballot review')
        if contest['status'] != 'review_required' and not review.get('replace_reported_general_matchup'):
            continue
        if review.get('replace_reported_general_matchup') is not None and (
                review['replace_reported_general_matchup'] is not True
                or contest['status'] not in ('review_required', 'reported_general_matchup')):
            raise SourceError('Invalid explicit official governor roster replacement')
        if (review['state'] != state or review['election_date'] != contest['election_date']
                or review['source_role'] != 'state_election_agency'
                or not review['source_url'].startswith('https://') or not review['evidence_note_ko']):
            raise SourceError('Governor ballot review scope/source mismatch')
        contest.update(status='reported_general_matchup', hold_reason=None,
            source_role='state_election_agency', coverage='complete_ballot',
            candidates=deepcopy(review['candidates']), source_url=review['source_url'],
            ballot_reviewed_on=review.get('reviewed_on', reviews['reviewed_on']),
            candidate_identity_basis='state_election_agency_general_ballot_listing',
            evidence_note_ko=review['evidence_note_ko'])
        contest.pop('poll_required_candidates', None)
        if 'poll_required_candidates' in review:
            contest['poll_required_candidates'] = deepcopy(review['poll_required_candidates'])
        sources = [s for s in sources if not (s.get('state') == state and s.get('source_url') == review['source_url'])]
        sources.append({'state': state, 'source_url': review['source_url'],
                        'reviewed_on': review.get('reviewed_on', reviews['reviewed_on']), 'source_role': review['source_role']})
    selected['additional_sources'] = sources
    selected['coverage'] = {'contest_count': len(selected['contests']),
        'reviewed_matchup_count': sum(c['status'] == 'reported_general_matchup' for c in selected['contests'].values()),
        'held_states': sorted(s for s, c in selected['contests'].items() if c['status'] == 'review_required')}
    note = 'NGA 누락 대진은 검토한 주 선거관리기관 본선 명부로 보완합니다. 보완 명부는 자동 API 수집기가 아닌 검토 스냅샷입니다.'
    if note not in selected['limitations_ko']:
        selected['limitations_ko'].append(note)
    validate_snapshot(selected, snapshot['cycle'], as_of)
    return selected


def validate_snapshot(snapshot, cycle, as_of):
    """Reject a future or inconsistent roster before either public consumer uses it."""
    if (snapshot.get('schema') != 'usa_governor_matchups_v1' or snapshot['cycle'] != cycle
            or date.fromisoformat(snapshot['reviewed_on']) > date.fromisoformat(as_of)):
        raise SourceError('Governor matchup snapshot schema/cycle/date mismatch')
    contests = snapshot['contests']
    if not contests or not set(contests) <= set(STATES):
        raise SourceError('Invalid governor roster state universe')
    held = []
    for state, contest in contests.items():
        if (contest['state'] != state or contest['election_date'] != f'{cycle}-11-03'
                or not f'{cycle}-01-01' <= contest['primary_date'] < contest['election_date']):
            raise SourceError('Governor contest scope/date mismatch')
        if date.fromisoformat(contest.get('ballot_reviewed_on', snapshot['reviewed_on'])) > date.fromisoformat(as_of):
            raise SourceError('Future governor candidate review')
        candidates = contest['candidates']
        if contest['status'] == 'review_required':
            if candidates or not contest['hold_reason']:
                raise SourceError('Held governor roster contains nominees')
            held.append(state)
            continue
        if contest['status'] != 'reported_general_matchup' or len(candidates) < 2:
            raise SourceError('Governor roster status/candidate count mismatch')
        if (len({c['candidate_id'] for c in candidates}) != len(candidates)
                or len({name_key(c['name']) for c in candidates}) != len(candidates)):
            raise SourceError('Duplicate governor roster identity')
        if 'poll_required_candidates' in contest:
            names=contest['poll_required_candidates']
            if not isinstance(names,list) or len(names)<2 or len(set(names))!=len(names) or not set(names)<= {c['name'] for c in candidates}:
                raise SourceError('Invalid explicitly reviewed governor poll comparison')
        if any(c['state'] != state or c['office'] != 'G' or c['election_year'] != cycle
               or c['party'] not in ROSTER_PARTIES or not c['candidate_id'] or not name_key(c['name'])
               for c in candidates):
            raise SourceError('Governor candidate scope mismatch')
    expected = {'contest_count': len(contests), 'reviewed_matchup_count': len(contests) - len(held),
                'held_states': sorted(held)}
    if snapshot['coverage'] != expected:
        raise SourceError('Governor roster coverage mismatch')


def apply_matchups(policy, snapshot, as_of):
    validate_snapshot(snapshot, policy['cycle'], as_of)
    selected = deepcopy(policy)
    for state, source in snapshot['contests'].items():
        rid = f'USA:{state}:governor'
        # Reviewed NGA nominees extend the election universe, never poll records.
        if rid not in selected['races']:
            selected['races'][rid] = {'state': state, 'office': 'governor', 'district': None,
                'subject': f'{policy["cycle"]} {source["state_name"]}', 'poll_type': 'governor',
                'seat_name': None, 'contest_id': f'{rid}:{policy["cycle"]}:general:regular',
                'general_from': f'{policy["cycle"]}-09-01', 'election_date': source['election_date'],
                'election_kind': 'regular', 'schedule_status': 'watch_slot_unverified',
                'required_candidates': [], 'candidates': {},
                'selection_reason_ko': '검토한 2026 주지사 선거 대진. 조사·지출 관측은 각각 별도 수집.'}
        race = selected['races'][rid]
        race['governor_roster'] = {'source_url': source['source_url'],
            'reviewed_on': source.get('ballot_reviewed_on', snapshot['reviewed_on']),
            'status': source['status'], 'hold_reason': source['hold_reason'], 'primary_date': source['primary_date'],
            'basis': source.get('candidate_identity_basis', 'reported_general_ballot_not_state_certification')}
        if source['status'] != 'reported_general_matchup':
            continue
        if race['required_candidates']:
            for name in race['required_candidates']:
                matches = [c for c in source['candidates'] if name_key(c['name']) == name_key(name)
                    and c['party'] == race['candidates'][name]['party']]
                if len(matches) != 1:
                    raise SourceError('Previously reviewed governor matchup conflicts with NGA snapshot')
                race['candidates'][name].update(candidate_id=matches[0]['candidate_id'],
                    identity_source_url=source['source_url'], identity_basis=matches[0]['candidate_identity_basis'])
        else:
            race['required_candidates'] = source.get('poll_required_candidates', [c['name'] for c in source['candidates']])
            race['candidates'] = {c['name']: {'party': c['party'], 'source_url': c['source_url'],
                'candidate_id': c['candidate_id'], 'identity_basis': c['candidate_identity_basis']}
                for c in source['candidates']}
            race['schedule_status'] = 'reported_general_matchup'
    selected['states'] = sorted(set(selected['states']) | set(snapshot['contests']))
    selected['governor_roster_coverage'] = deepcopy(snapshot['coverage'])
    return selected
