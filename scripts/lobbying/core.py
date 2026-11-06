"""Source-preserving FARA/LDA normalization. No country or industry intake filter."""
import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime
from urllib.parse import urlparse

VERSION = 'lobbying-v1'
COUNTRIES = {'KOREA, SOUTH': 'KR', 'SOUTH KOREA': 'KR', 'JAPAN': 'JP',
             'CHINA': 'CN', 'TAIWAN': 'TW', 'HONG KONG': 'HK', 'MACAU': 'MO'}
TOPICS = {
    'supply_chain': r'\bsupply chains?\b|\breshoring\b|\bbuy america\b|\bsourcing\b',
    'mining': r'\bmining\b|\bcritical minerals?\b|\brare earths?\b|\blithium\b|\bnickel\b',
    'agriculture': r'\bagricultur\w*\b|\bfarm bill\b|\bcrop insurance\b|\bsoybeans?\b|\bfertilizers?\b',
    'semiconductors': r'\bsemiconductors?\b|\bCHIPS\b|\bfoundr(?:y|ies)\b',
    'data_centers': r'\bdata\s*cent(?:er|re)s?\b|\bhyperscal\w*\b',
    'steel': r'\bsteel\w*\b',
}


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def source_date(value):
    if not value:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            date = datetime.strptime(str(value)[:10], fmt)
            # Source has malformed years (e.g. 0200). Preserve raw; never invent a date.
            return date.date().isoformat() if 1900 <= date.year <= 2100 else None
        except ValueError:
            pass
    return None


def tags(text):
    return [key for key, pattern in TOPICS.items() if re.search(pattern, text or '', re.I)]


def country_code(raw):
    raw = (raw or '').strip()
    return COUNTRIES.get(raw.upper(), raw.upper() if re.fullmatch('[A-Za-z]{2}', raw) else None)


def official_url(url, source):
    parsed = urlparse(url or '')
    allowed = {'fara': {'efile.fara.gov'}, 'lda': {'lda.gov', 'lda.senate.gov'}}[source]
    if parsed.scheme != 'https' or parsed.hostname not in allowed or parsed.username or parsed.password:
        raise ValueError('Unexpected official source URL')
    return url


def read_bulk(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith('.csv')]
        if len(names) != 1 or archive.getinfo(names[0]).file_size > 200_000_000:
            raise ValueError('Unexpected FARA bulk archive')
        # DOJ documents Latin-1. utf-8 BOM is accepted when actually present.
        raw = archive.read(names[0])
    text = raw.decode('utf-8-sig') if raw.startswith(b'\xef\xbb\xbf') else raw.decode('latin-1')
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        extra = row.pop(None, None)
        if extra is not None or any(value is None for value in row.values()):
            row['_source_parse_status'] = 'column_mismatch'
            if extra is not None:
                row['_unparsed_extra_fields'] = extra
        rows.append(row)
    return rows


def fara_record(row, kind, registration_countries=None):
    reg = str(row.get('Registration Number', '')).strip()
    partial = not reg.isdigit() or row.get('_source_parse_status') == 'column_mismatch'
    if partial:
        reg = None
    url = row.get('URL')
    office_only = kind == 'document' and url == 'Available-FARA-Public-Office'
    if partial:
        identity = ['partial', kind, row]
        url = None
    elif kind == 'document':
        if office_only:
            identity = row
            url = None
        else:
            official_url(url, 'fara')
            identity = url
    elif kind == 'registrant':
        identity = reg
    elif kind == 'principal':
        identity = [reg, row.get('Foreign Principal'), row.get('Foreign Principal Registration Date'), row.get('Country/Location Represented')]
    elif kind == 'person':
        identity = [reg, row.get('Short Form First Name'), row.get('Short Form Last Name'), row.get('Short Form Date')]
    else:
        raise ValueError('Unknown FARA kind')
    raw_country = None if partial else row.get('Foreign Principal Country') or row.get('Country/Location Represented') or None
    code = country_code(raw_country)
    date = row.get('Date Stamped') or row.get('Foreign Principal Registration Date') or row.get('Short Form Date') or row.get('Registration Date')
    return {
        'record_id': 'fara:' + kind + ':' + digest(identity), 'source': 'fara', 'kind': kind,
        'source_url': url or ('https://efile.fara.gov/ords/fara/f?p=1381:200:::NO:RP,200:P200_REG_NUMBER:' + reg if reg else 'https://efile.fara.gov/'),
        'source_date': source_date(date), 'registrant_id': reg,
        'registrant_name': None if partial else row.get('Registrant Name') or row.get('Name'),
        'client_name': None if partial else row.get('Foreign Principal Name') or row.get('Foreign Principal'),
        'title': '원천 CSV 정규화 검토 필요' if partial else row.get('Document Type') or row.get('Foreign Principal') or row.get('Name') or ' '.join(filter(None, [row.get('Short Form First Name'), row.get('Short Form Last Name')])),
        'country_raw': raw_country, 'country_codes': [code] if code else [],
        'related_countries': sorted((registration_countries or {}).get(reg, [])),
        'text_state': ('source_unavailable' if office_only else 'pending') if kind == 'document' else 'not_applicable',
        'raw_payload': row, 'payload_hash': digest(row), 'topics': [],
    }


def fara_records(rows, kind, countries=None):
    """Keep conflicting source observations together instead of last-row-wins."""
    by_id = {}
    observations = {}
    for row in rows:
        record = fara_record(row, kind, countries)
        rid = record['record_id']
        by_id.setdefault(rid, record)
        observations.setdefault(rid, {})[digest(row)] = row
    for rid, versions in observations.items():
        if len(versions) > 1:
            payload = {'_source_parse_status': 'conflicting_observations',
                       '_observations': [versions[key] for key in sorted(versions)]}
            by_id[rid].update(raw_payload=payload, payload_hash=digest(payload))
    return sorted(by_id.values(), key=lambda row: row['record_id'])


def policy_refs(text, evidence):
    """Only explicit identifiers. A report year never supplies a missing Congress."""
    refs = []
    for m in re.finditer(r'\b(H\s*\.?\s*R\s*\.?|S\s*\.)(?:\s*)(\d+)\b', text or '', re.I):
        context = text[max(0, m.start()-100):m.end()+100]
        congresses = set(re.findall(r'\b(\d{3})(?:st|nd|rd|th)\s+Congress\b', context, re.I))
        congress = next(iter(congresses)) if len(congresses) == 1 else None
        typ = 'hr' if m.group(1).lower().startswith('h') else 's'
        target = f'{congress}-{typ}-{int(m.group(2))}' if congress else None
        refs.append({'reference_key': digest([m.group(0), evidence]), 'target_type': 'bill',
                     'target_id': target, 'raw_reference': m.group(0),
                     'resolution_status': 'explicit_identifier' if target else 'ambiguous',
                     'evidence': evidence})
    for pattern, kind in [(r'\b(?:P\.?\s*L\.?|Public Law)\s*(\d{3})[-–](\d+)\b', 'public_law'),
                          (r'\b(?:Executive Order|E\.?\s*O\.?)\s*(\d{4,5})\b', 'executive_order')]:
        for m in re.finditer(pattern, text or '', re.I):
            target = f'{m.group(1)}-public-{m.group(2)}' if kind == 'public_law' else m.group(1)
            refs.append({'reference_key': digest([m.group(0), evidence]), 'target_type': kind,
                         'target_id': target, 'raw_reference': m.group(0),
                         'resolution_status': 'explicit_identifier', 'evidence': evidence})
    return refs


def lda_record(row):
    required = ['filing_uuid', 'filing_type', 'registrant', 'client']
    if any(key not in row for key in required) or not isinstance(row['registrant'], dict) or not isinstance(row['client'], dict):
        raise ValueError('LDA payload schema not recognized; cursor held')
    uid = str(row['filing_uuid'])
    if not re.fullmatch(r'[a-fA-F0-9-]{36}', uid):
        raise ValueError('Invalid LDA UUID')
    url = row.get('filing_document_url') or f'https://lda.gov/filings/public/filing/{uid}/print/'
    official_url(url, 'lda')
    activities, refs = [], []
    for index, block in enumerate(row.get('lobbying_activities') or []):
        text = block.get('description') or ''
        evidence = {'json_path': f'$.lobbying_activities[{index}].description'}
        activities.append({'activity_id': f'lda:{uid}:{index}', 'grain': 'filing_issue_block',
                           'description': text, 'issue_code': block.get('general_issue_code'),
                           'government_entities': block.get('government_entities') or [],
                           'lobbyists': block.get('lobbyists') or [], 'topics': tags(text),
                           'evidence': evidence})
        refs.extend(policy_refs(text, evidence))
    body = '\n\n'.join(a['description'] for a in activities)
    raw_country = row['client'].get('country')
    code = country_code(raw_country)
    return {'record_id': 'lda:' + uid, 'source': 'lda', 'kind': 'document', 'source_url': url,
            'source_date': source_date(row.get('dt_posted')), 'registrant_id': str(row['registrant'].get('id', '')),
            'registrant_name': row['registrant'].get('name'), 'client_name': row['client'].get('name'),
            'title': row.get('filing_type_display') or row['filing_type'],
            'country_raw': raw_country, 'country_codes': [code] if code else [], 'related_countries': [],
            'topics': tags(body), 'text_state': 'extracted', 'body_text': body,
            'raw_payload': row, 'payload_hash': digest(row), 'activities': activities, 'references': refs}
