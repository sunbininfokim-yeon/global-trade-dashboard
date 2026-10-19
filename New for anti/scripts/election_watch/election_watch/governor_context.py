"""Election schedule and incumbent availability, independent of polling/spending."""
from collections import Counter
from copy import deepcopy
from datetime import date
import hashlib
from html import unescape
import re

from .polls import require


def identity(name):
    return re.sub(r'[^a-z0-9]', '', (name or '').casefold())


def parse_nga(html, inputs, catalog, captured_at):
    result = deepcopy(inputs); found = {}
    for state, body in re.findall(r'<div\b[^>]*data-original-id="US-([A-Z]{2})"[^>]*>(.*?)</div>', html, re.S):
        heading = re.search(r'<h3\b[^>]*>(.*?)</h3>', body, re.S)
        if not heading or f'gubernatorial_election,_{inputs["cycle"]}' not in heading[1] or state not in catalog['states']:
            continue
        require(state not in found, 'duplicate governor context panel')
        text = ' '.join(unescape(re.sub('<[^>]+>', ' ', body)).split())
        incumbent = re.search(r'Incumbent: Gov\. (.*?) Length of Regular Terms:', text)
        require(incumbent, 'governor context incumbent missing')
        found[state] = {'incumbent_name': incumbent[1].rstrip('*'),
                        'term_limited_reported': True if '* Term Limited' in text else None}
    require(set(found) == set(catalog['governor_states']) == set(inputs['contests']),
            'changed governor context election universe')
    require(found == inputs['contests'], 'governor incumbent/term status changed; manual review required')
    result['source'] = {**inputs['source'], 'captured_at': captured_at,
                        'sha256': hashlib.sha256(html.encode()).hexdigest()}
    return result


def build_context(inputs, catalog, state_cards, as_of):
    day = date.fromisoformat(as_of)
    require(inputs['schema'] == 'usa_governor_context_inputs_v1' and inputs['cycle'] == catalog['cycle'] == 2026,
            'governor context cycle/schema')
    require(date.fromisoformat(inputs['reviewed_on']) <= day, 'future governor context')
    require(set(inputs['contests']) == set(catalog['governor_states']) and len(inputs['contests']) == 36,
            'governor context universe')
    require(len(catalog['states']) == 50 and {c['id'] for c in state_cards} == set(catalog['states']),
            'governor context requires all fifty state cards')
    require(inputs['election_date'] == '2026-11-03', 'governor election date')
    states = {}
    for card in state_cards:
        state = card['id']; entry = inputs['contests'].get(state)
        incumbent = card.get('governor') or {}
        status = 'not_on_cycle_ballot' if entry is None else 'not_verified'
        limited = None; source = deepcopy(inputs['source']); review_day = inputs['reviewed_on']
        if entry:
            require(entry['term_limited_reported'] in (True, None), 'unknown term limit flag')
            if identity(incumbent.get('name')) != identity(entry['incumbent_name']):
                status = 'incumbent_identity_conflict'
            elif entry['term_limited_reported'] is True:
                status = 'term_limited_reported'; limited = True
            else:
                review = inputs.get('incumbent_status_reviews', {}).get(state)
                if review:
                    require(review['status'] in ('not_seeking_reelection_reported', 'primary_defeated_reported')
                            and identity(review['incumbent_name']) == identity(entry['incumbent_name'])
                            and date.fromisoformat(review['reviewed_on']) <= day, 'invalid incumbent status review')
                    status = review['status']; source = deepcopy(review); review_day = review['reviewed_on']
        states[state] = {'state': state, 'cycle': inputs['cycle'], 'election_in_cycle': entry is not None,
            'race_id': f'USA:{state}:governor' if entry else None,
            'election_date': inputs['election_date'] if entry else None,
            'incumbent': deepcopy(incumbent), 'incumbent_ballot_status': status,
            'term_limited_reported': limited, 'reviewed_on': review_day, 'source': source,
            'legal_rule_review': deepcopy(inputs.get('legal_rule_reviews', {}).get(state))}
    counts = Counter(r['incumbent_ballot_status'] for r in states.values())
    return {'schema': 'usa_governor_election_context_v1', 'cycle': inputs['cycle'],
        'reviewed_on': inputs['reviewed_on'], 'scope': '50_states_not_territories',
        'counts': {'all_states': 50, 'contested': 36, 'not_contested': 14,
                   'term_limited_reported': counts['term_limited_reported'],
                   'by_incumbent_status': dict(counts)}, 'states': states,
        'limitations_ko': deepcopy(inputs['limitations_ko'])}
