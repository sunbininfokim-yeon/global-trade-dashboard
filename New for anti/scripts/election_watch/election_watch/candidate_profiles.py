"""State-owned, per-field candidate biographies; no demographic inference."""
from copy import deepcopy
from datetime import date
from .polls import require, https_url

FIELDS = ('birth_date', 'race_ethnicity', 'military_service', 'career')


def validate_profiles(doc, state, as_of):
    require(doc['schema'] == 'usa_candidate_profiles_v1' and doc['state'] == state
            and doc['cycle'] == 2026, 'candidate profile scope')
    require(date.fromisoformat(doc['reviewed_on']) <= date.fromisoformat(as_of), 'future candidate biography')
    seen = set()
    for person in doc['people']:
        key = (person['office'], person['name'], person['party'])
        require(person['office'] in ('governor', 'senate') and person['name'] and person['party']
                and key not in seen, 'ambiguous candidate profile identity')
        seen.add(key)
        for name in FIELDS:
            field = person[name]
            require(field['status'] in ('verified', 'self_reported', 'not_verified', 'source_unavailable'),
                    'candidate biography field status')
            if field['value'] is None:
                require(field['status'] in ('not_verified', 'source_unavailable'), 'verified biography cannot be null')
            else:
                require(field['status'] in ('verified', 'self_reported') and https_url(field['source_url'])
                        and date.fromisoformat(field['reviewed_on']) <= date.fromisoformat(as_of)
                        and field.get('evidence_locator'), 'unsourced candidate biography field')
                if name == 'race_ethnicity':
                    require(field.get('identity_basis') in ('explicit_self_identification', 'explicit_official_biography'),
                            'inferred race or ethnicity is not evidence')
                if name == 'birth_date':
                    require(field.get('precision') == 'day', 'unverified birth-date precision')
                    born = date.fromisoformat(field['value'])
                    require(born <= date.fromisoformat(as_of), 'future candidate birth date')
    return doc


def attach_profiles(state_cards, packets, as_of):
    cards = deepcopy(state_cards); by_state = {c['id']: c for c in cards}
    for packet in packets:
        doc = packet.get('candidate_profiles')
        if not doc: continue
        state = packet['state']; validate_profiles(doc, state, as_of)
        require(state in by_state, 'candidate profile without state card')
        card = by_state[state]; unmatched = []
        for person in doc['people']:
            rid = f'USA:{state}:{person["office"]}'
            roster = card.get('election_matchups', {}).get(rid, {})
            matches = [c for c in roster.get('candidates', [])
                       if c['name'] == person['name'] and c['party'] == person['party']]
            if len(matches) != 1 or (person.get('candidate_id')
                    and person['candidate_id'] != matches[0].get('candidate_id')):
                unmatched.append({'name': person['name'], 'race_id': rid, 'status': 'profile_roster_identity_unresolved'})
                continue
            profile = deepcopy(person); born = profile['birth_date']['value']
            if born:
                today, birthday = date.fromisoformat(as_of), date.fromisoformat(born)
                profile['age'] = {'value': today.year-birthday.year-((today.month,today.day)<(birthday.month,birthday.day)),
                                  'as_of': as_of, 'basis': 'verified_birth_date'}
            else:
                profile['age'] = {'value': None, 'as_of': None, 'basis': 'birth_date_not_verified'}
            profile['identity_basis'] = 'exact_reviewed_roster_name_party_office_state_cycle'
            matches[0]['biography'] = profile
        card['candidate_profile_coverage'] = {'reviewed_on': doc['reviewed_on'],
            'input_people': len(doc['people']), 'linked_people': len(doc['people'])-len(unmatched),
            'unmatched': unmatched, 'note_ko': '일부 확인된 약력이며 인종·군 경력·생일 미확인을 추정으로 채우지 않음.'}
    return cards
