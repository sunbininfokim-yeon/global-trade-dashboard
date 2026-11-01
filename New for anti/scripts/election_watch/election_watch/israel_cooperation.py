"""Qualitative party features and scoped, dated evidence, never compatibility scores."""
from datetime import date
from urllib.parse import urlparse


def validate_cooperation(data, known):
    def check(ok, message):
        if not ok:
            raise ValueError('cooperation review: ' + message)
    check(data.get('schema') == 'israel_cooperation_review_v1', 'wrong schema')
    reviewed = date.fromisoformat(data['reviewed_on'])
    sources = data['sources']
    for source in sources.values():
        u = urlparse(source['url'])
        check(u.scheme == 'https' and u.hostname and not u.username and not u.password, 'unsafe source')
        check(type(source.get('body_opened')) is bool and date.fromisoformat(source['checked_on']) <= reviewed, 'invalid receipt')
    def references(row):
        check(row.get('source_ids') and all(sources.get(id, {}).get('body_opened') for id in row['source_ids']), 'source body not reviewed')
    profiles = data['profiles']
    ids = [p['list_id'] for p in profiles]
    check(len(set(ids)) == len(ids) and set(ids) <= known, 'duplicate or unknown party')
    for p in profiles:
        check(p.get('spectrum') in {'left', 'center', 'right', 'far-right', 'plural', 'unplaced'}, 'unknown spectrum family')
        check(p.get('religion_ko') and p.get('spectrum_ko') and p.get('issues_ko'), 'missing qualitative features')
        references(p)
        components = p.get('components', [])
        check(len({c['id'] for c in components}) == len(components), 'duplicate component')
        for c in components:
            check(c.get('seats') is None, 'unverified component seats must stay null')
            references(c)
    relations = data['relations']
    check(len({r['id'] for r in relations}) == len(relations), 'duplicate relation')
    for r in relations:
        check(len(set(r['parties'])) == len(r['parties']) and len(r['parties']) >= 2 and set(r['parties']) <= set(ids), 'invalid participants')
        check(r.get('kind') in {'talks', 'refusal', 'joint_principles'} and r.get('phase') in {'pre_election', 'post_election'}, 'unsupported relationship claim')
        day = date.fromisoformat(r['event_date'])
        check(day <= reviewed and ((day >= date(2026, 10, 27)) == (r['phase'] == 'post_election')), 'wrong evidence phase')
        check(r.get('limit_ko') and r.get('basis_ko'), 'missing scope of claim')
        references(r)
    return data
