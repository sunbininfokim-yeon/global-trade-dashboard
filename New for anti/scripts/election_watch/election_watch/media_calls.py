"""Election-night media calls (AP 등, 비공식): validation shared by CI and the entry tool."""
from datetime import datetime, timezone
import re

POLLS_CLOSE = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)  # earliest poll close (ET 18:00)
RACE = re.compile(r'^USA:[A-Z]{2}:(?:governor|senate|house:\d{2})$')


def resolve_reviewed_party_call(race, party):
    """Resolve an explicit media party win, never a lead, against the ballot roster."""
    poll_types = {'senate': 'us-senator', 'governor': 'governor', 'house': 'us-representative'}
    if (party not in ('DEM', 'REP', 'IND') or race.get('election_date') != '2026-11-03'
            or race.get('office') not in poll_types or race.get('poll_type') != poll_types[race['office']]):
        raise ValueError('wrong party/election scope')
    candidates = [(v.get('canonical_name') or n, v) for n, v in race.get('candidates', {}).items() if v.get('party') == party]
    names = {n.strip() for n, _ in candidates if isinstance(n, str) and n.strip()}
    if len(names) != 1:
        raise ValueError(f'called party has {len(names)} distinct candidates')
    winner = next(iter(names))
    review = race.get('ballot_review') or {}
    if review.get('source_url', '').startswith('https://') and review.get('reviewed_on'):
        return winner, {'method': 'unique_reviewed_ballot_candidate_for_called_party',
                        'source_url': review['source_url'], 'reviewed_on': review['reviewed_on']}
    # The existing governor registry separately documents full name/party/office/cycle.
    for _, candidate in candidates:
        url = candidate.get('identity_source_url') or candidate.get('source_url') or ''
        if (race.get('office') == 'governor'
                and candidate.get('identity_basis') == 'NGA_general_candidate_section_full_name_party_office_cycle'
                and url == 'https://www.nga.org/governors/elections/'):
            return winner, {'method': 'unique_reviewed_nga_candidate_for_called_party', 'source_url': url}
    raise ValueError('candidate identity source not reviewed')


def check(data, ratings, certified, now):
    """Return a list of problems; empty means the file is publishable."""
    problems = []
    if data.get('schema') != 'usa_election_media_calls_v1' or data.get('cycle') != 2026:
        return ['schema/cycle']
    known = {r['race_id'] for office in ratings['offices'].values() for r in office['races']}
    seen = set()
    for i, c in enumerate(data.get('calls', [])):
        tag = f"{i}:{c.get('race_id')}"
        if not RACE.match(c.get('race_id') or '') or c['race_id'] not in known:
            problems.append(f'{tag} unknown race')
        if c.get('race_id') in seen:
            problems.append(f'{tag} duplicate race')
        seen.add(c.get('race_id'))
        status = c.get('status')
        if status not in ('called', 'runoff', 'retracted'):
            problems.append(f'{tag} status')
        if status == 'called' and (c.get('party') not in ('DEM', 'REP', 'IND') or not (c.get('winner') or '').strip()):
            problems.append(f'{tag} winner/party')
        if not c.get('called_by') or not all(isinstance(x, str) and x.strip() for x in c['called_by']):
            problems.append(f'{tag} called_by')
        if not (c.get('source_url') or '').startswith('https://'):
            problems.append(f'{tag} source_url')
        if c.get('winner_resolution_ref'):
            proof = data.get('candidate_identity_sources', {}).get(c['winner_resolution_ref'])
            if not proof or not str(proof.get('source_url') or '').startswith('https://'):
                problems.append(f'{tag} missing candidate identity evidence')
        # Public reporting may establish the winner without an exact AP call time.
        # Preserve that missing time; never invent one from article/update dates.
        time_field = 'called_at'
        if c.get('called_at') is None and c.get('call_time_status') == 'not_reported':
            time_field = 'verified_at'
        try:
            at = datetime.fromisoformat(c[time_field].replace('Z', '+00:00'))
            if at.tzinfo is None or at < POLLS_CLOSE or at > now:
                problems.append(f'{tag} {time_field} window')
        except (KeyError, ValueError, AttributeError):
            problems.append(f'{tag} {time_field}')
        cert = certified.get(c.get('race_id'))
        if cert and status == 'called' and cert.get('party') and cert['party'] != c.get('party'):
            problems.append(f'{tag} contradicts certified result')
    return problems
