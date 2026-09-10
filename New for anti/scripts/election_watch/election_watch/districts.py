"""Auditable map-only normalization; raw FEC source shards remain unchanged."""
from collections import defaultdict
import re


def district_code(value):
    # Missing is not a reported statewide/at-large code.
    return str(value).zfill(2) if value not in (None, '') else 'UNKNOWN'


def normalize_house(rows, roster, geometry, cycle):
    master = defaultdict(set)
    for c in roster:
        if c.get('office') == 'H' and c.get('election_year') == int(cycle):
            master[c['candidate_id']].add((c['state'], district_code(c.get('district'))))

    def one(record, registration=False):
        if record.get('office') not in ('H', 'house'):
            return dict(record)
        r = dict(record)
        state, district = r['state'], district_code(r.get('district'))
        original = (state, district)
        status = 'reported_geometry_match' if original in geometry else 'reported_geometry_unmatched'
        evidence = None
        # Candidate master must be unique, same election year, and point to an existing shape.
        # Never infer a location from the digits embedded in an FEC candidate ID.
        choices = master.get(r['candidate_id'], set())
        phase_year = re.search(r'(\d{4})$', r.get('election_type') or '')
        if (not registration and original not in geometry and len(choices) == 1
                and phase_year and int(phase_year[1]) == int(cycle)):
            target = next(iter(choices))
            if target in geometry:
                state, district = target
                status = 'candidate_master_normalized'
                evidence = f'https://www.fec.gov/files/bulk-downloads/{cycle}/cn{str(cycle)[-2:]}.zip'
        if status != 'candidate_master_normalized':
            state_shapes = {d for s, d in geometry if s == state}
            if district in ('00', '01') and state_shapes == {'00'}:
                district = '00'
                status = 'at_large_code_normalized' if original[1] != district else status
            elif state == 'DC' and district in ('00', '01') and state_shapes == {'98'}:
                district, status = '98', 'delegate_code_normalized'
            elif original not in geometry:
                status = ('missing_district' if district == 'UNKNOWN' else
                          'geometry_unavailable' if not state_shapes else
                          'invalid_fec_registration_district' if registration else 'unresolved_reported_district')
        r.update(state=state, district=district)
        r['district_source'] = {'status': status, 'reported_state': record['state'],
            'reported_district': record.get('district'), 'normalized_state': state,
            'normalized_district': district, 'source_kind': 'fec_candidate_master' if registration else 'fec_schedule_e',
            'evidence_url': evidence, 'boundary_election_match_verified': False}
        return r
    return [one(r) for r in rows], [one(c, True) for c in roster]


def district_audit(rows, roster):
    result = []
    for record in rows + roster:
        source = record.get('district_source')
        if source and source['status'] != 'reported_geometry_match':
            result.append({'candidate_id': record['candidate_id'], 'district_source': source,
                'source_url': record.get('source_url'), 'records': record.get('records', 0),
                'support_cents': record.get('support_cents'), 'oppose_cents': record.get('oppose_cents')})
    return result
