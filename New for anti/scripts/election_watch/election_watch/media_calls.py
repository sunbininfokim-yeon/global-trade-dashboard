"""Election-night media calls (AP 등, 비공식): validation shared by CI and the entry tool."""
from datetime import datetime, timezone
import re

POLLS_CLOSE = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)  # earliest poll close (ET 18:00)
RACE = re.compile(r'^USA:[A-Z]{2}:(?:governor|senate|house:\d{2})$')


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
        try:
            at = datetime.fromisoformat(c['called_at'].replace('Z', '+00:00'))
            if at.tzinfo is None or at < POLLS_CLOSE or at > now:
                problems.append(f'{tag} called_at window')
        except (KeyError, ValueError, AttributeError):
            problems.append(f'{tag} called_at')
        cert = certified.get(c.get('race_id'))
        if cert and status == 'called' and cert.get('party') and cert['party'] != c.get('party'):
            problems.append(f'{tag} contradicts certified result')
    return problems
