"""Separate reported election counts from accepted polling and government events."""
from datetime import date
from urllib.parse import urlparse


def validate_results(data, known):
    def require(condition, message):
        if not condition:
            raise ValueError('post-election: ' + message)

    require(data.get('schema') == 'israel_post_election_v1' and data.get('cycle') == 'knesset-26', 'wrong schema or cycle')
    reviewed = date.fromisoformat(data['evidence_as_of'])
    require(date.fromisoformat(data['result_as_of']) <= reviewed, 'future count')
    require(data.get('review_status') == 'partial' and data.get('official_table_verified') is False,
            'reported count cannot become certified results')
    require(all(data.get(key) is None for key in ('official_certification_date', 'mandate_holder', 'mandate_date', 'government_formed'))
            and data.get('government_status') == 'unverified', 'unverified political events must remain null')
    row = data['result_record']
    require(row.get('question_id') == 'official_results' and row.get('review_status') == 'partial'
            and row.get('average_eligible') is False and row.get('unit') == 'seats'
            and row.get('cycle') == 'knesset-26', 'count must stay separate from accepted polls')
    values = row.get('values', [])
    ids = [value.get('list_id') for value in values]
    require(values and len(set(ids)) == len(ids) and set(ids) <= known, 'unknown or duplicate list')
    require(all(type(v.get('seats')) is int and 0 < v['seats'] <= 120 for v in values)
            and sum(v['seats'] for v in values) == 120 and row.get('seat_sum') == 120, 'count must total 120')
    votes = row['votes']
    require(all(type(votes.get(k)) is int and votes[k] > 0 for k in ('counted', 'valid', 'invalid'))
            and votes['valid'] + votes['invalid'] == votes['counted'], 'inconsistent vote counts')
    require(type(votes.get('turnout_pct')) in (int, float) and 0 <= votes['turnout_pct'] <= 100, 'invalid turnout')
    blocs = [row.get('bloc_as_published', {}).get(k) for k in ('current_coalition', 'opposition', 'arab')]
    require(all(type(n) is int and n >= 0 for n in blocs) and sum(blocs) == 120, 'invalid reported blocs')
    sources = data.get('sources', [])
    source_map = {s['id']: s for s in sources}
    require(len(source_map) == len(sources), 'duplicate source')
    for source in sources:
        parsed = urlparse(source.get('url', ''))
        require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password, 'invalid source URL')
        require(type(source.get('body_opened')) is bool and date.fromisoformat(source['checked_on']) <= reviewed, 'invalid source receipt')
    require(any(s['url'] == row.get('source_url') and s['body_opened'] for s in sources), 'count source body not reviewed')
    for step in data['steps'] + data['fallback']:
        require(step.get('source_ids') and all(source_map.get(id, {}).get('body_opened') for id in step['source_ids']), 'unreviewed procedure source')
    for step in data['steps']:
        require(step.get('status') in ('conditional', 'reported_scheduled', 'reported_expected'), 'unsupported event completion')
        require((step['date'] is None) == (step['status'] == 'conditional'), 'conditional deadline must stay null')
        if step['date']:
            date.fromisoformat(step['date'])
    return data
