"""Evidence-aware policy screening, NOT a customs classification/clearance engine.

Trade volumes cannot establish whether exports are lawful. HS overlap only
raises a candidate; permits, grade, end use, destination and exemptions matter.
No match, stale evidence, missing dates or unavailable sources never mean clear.
"""
from datetime import date
import calendar
from urllib.parse import urlsplit

# Only unambiguous product-form mappings; ambiguous seed labels stay unmapped.
SEED_HS = {
    'idn-nickel-ore': ['2604'], 'idn-bauxite': ['2606'],
    'idn-copper-concentrate': ['2603'], 'chn-graphite': ['2504'],
    'rus-wheat': ['1001'],
    'ind-wheat': ['1001'], 'arg-grains': ['1001', '1005', '1201'],
    'cod-cobalt': ['2605', '8105'], 'moz-graphite': ['2504'],
}


def with_documents(catalogue, documents):
    """Link scoped historical evidence without modifying the user's seed."""
    from copy import deepcopy
    out = deepcopy(catalogue)
    by_id = {d['rule_id']: d for d in documents.get('documents', [])}
    for rule in out.get('controls', []):
        doc = by_id.get(rule.get('id'))
        if doc:
            rule['legacy_source_url'] = rule.get('url')
            rule['url'] = doc['url']
            rule['hs_prefixes'] = doc['hs_prefixes']
            if doc.get('effective_from'):
                rule['effective_from'] = doc['effective_from']
            # A past announcement does not establish present validity.
            rule['official_document_verified'] = False
            rule['scope_verified'] = False
    return out


def period_bounds(period, frequency):
    y = int(period[:4])
    if frequency == 'A':
        return date(y, 1, 1), date(y, 12, 31)
    m = int(period[4:])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def screen(*, exporter_iso3, importer_iso3, hs, period, frequency, catalogue, as_of, monitor=None):
    start, end = period_bounds(period, frequency)
    today = date.fromisoformat(as_of)
    candidates = []
    for rule in catalogue.get('controls', []):
        if rule.get('iso') != exporter_iso3:
            continue
        prefixes = rule.get('hs_prefixes') or SEED_HS.get(rule.get('id'), [])
        if not prefixes or not any(hs.startswith(p) or p.startswith(hs) for p in prefixes):
            continue
        destinations = rule.get('destinations')
        if destinations and importer_iso3 and importer_iso3 not in destinations:
            continue
        scope = 'within_hs_scope' if any(hs.startswith(p) for p in prefixes) else 'broader_than_controlled_product'
        issues = []
        if not rule.get('scope_verified'):
            issues.append('product_scope_unverified')
        if scope == 'broader_than_controlled_product':
            issues.append('only_part_of_hs_may_be_controlled')
        if destinations and not importer_iso3:
            issues.append('destination_unknown')
        if not rule.get('official_document_verified'):
            issues.append('official_document_not_verified')
        temporal = 'unknown'
        try:
            since = date.fromisoformat(rule['effective_from'])
            until = date.fromisoformat(rule['effective_to']) if rule.get('effective_to') else None
            if since > end:
                temporal = 'not_yet_effective'
            elif until and until < start:
                temporal = 'ended_before_period'
            elif since > start or (until and until < end):
                temporal = 'part_of_period'
            else:
                temporal = 'overlaps_period'
        except (KeyError, ValueError, TypeError):
            issues.append('effective_dates_unverified')
        try:
            if date.fromisoformat(rule['review_valid_until']) < today:
                issues.append('legal_review_stale')
        except (KeyError, ValueError, TypeError):
            issues.append('current_legal_status_unverified')
        check = (monitor or {}).get('sources', {}).get(rule.get('url'), {})
        if check.get('status') in {'changed', 'unavailable'}:
            issues.append('source_' + check['status'])
        active_evidence = not issues and temporal in {'overlaps_period', 'part_of_period'}
        candidates.append({'id': rule.get('id'), 'exporter_iso3': exporter_iso3,
                           'level': rule.get('level'), 'product_form': rule.get('product_form'),
                           'hs_match': scope, 'temporal_status': temporal,
                           'status': 'verified_measure_scope' if active_evidence else 'requires_review',
                           'issues': issues, 'source_url': rule.get('url'),
                           'measure_ko': rule.get('measure_ko'), 'seed_as_of': rule.get('verified_as_of'),
                           'conditions': rule.get('conditions', []),
                           'source_check': check})
    return {'status': 'potential_control_match' if candidates else 'not_assessed',
            'checked_as_of': as_of, 'catalogue_as_of': catalogue.get('as_of'),
            'candidates': candidates, 'legal_clearance': None,
            'note_ko': 'HS·기간 기준 통제 후보입니다. 미매칭은 통제 없음이 아니며 허가·예외·최종용도는 별도 확인해야 합니다.'}


def coverage(catalogue):
    rules = catalogue.get('controls', [])
    return {'rule_count': len(rules),
            'unmapped_rule_ids': [r.get('id') for r in rules if not (r.get('hs_prefixes') or SEED_HS.get(r.get('id')))],
            'worldwide_coverage_verified': False}
