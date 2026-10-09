"""Bounded, unauthenticated discovery of Iowa's public IE report PDFs.

The public list has no candidate, direction or amount fields. Discovery cannot
produce candidate spending totals; those require reviewed PDF transactions.
"""
from datetime import date
import hashlib
import json
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .polls import require

API = 'https://webapp.iecdb.iowa.gov/api/publicreports/ie'
# Date ties overlap across live pages. Use one bounded response and explicitly
# retain partial coverage rather than deduplicating away unseen reports.
PAGE_SIZE = 100
MAX_PAGES = 1


def collect(checked_at, opener=urlopen):
    day = date.fromisoformat(checked_at[:10])
    require(day.year == 2026, 'Iowa report discovery cycle')
    records, receipts, seen = [], [], set()
    counts = None
    boundary = False
    previous_date = None
    for page in range(MAX_PAGES):
        query = {'pageLength': PAGE_SIZE, 'page': page, 'sortField': 'date',
                 'sortOrder': 'descend', 'echo': page + 1, 'filters': [], 'globalFilter': ''}
        request = Request(API, data=json.dumps(query).encode(), method='POST',
                          headers={'User-Agent': 'ElectionWatch/1.0 public-source-review',
                                   'Accept': 'application/json', 'Content-Type': 'application/json'})
        with opener(request, timeout=25) as response:
            require(response.status == 200 and response.geturl() == API, 'Iowa public API response')
            body = response.read(2 * 1024 * 1024 + 1)
        require(len(body) <= 2 * 1024 * 1024, 'oversized Iowa report list')
        data = json.loads(body)
        require(type(data.get('totalCount')) is int and type(data.get('filteredCount')) is int
                and data['totalCount'] == data['filteredCount'] >= 0
                and isinstance(data.get('results'), list) and data.get('echo') == page + 1,
                'Iowa report list schema')
        current_counts = (data['totalCount'], data['filteredCount'])
        require(counts is None or counts == current_counts, 'Iowa report list changed during pagination')
        counts = current_counts
        rows = data['results']
        require(len(rows) == min(PAGE_SIZE, max(0, counts[0] - page * PAGE_SIZE)),
                'incomplete Iowa report page')
        receipts.append({'page': page, 'sha256': hashlib.sha256(body).hexdigest(),
                         'response_bytes': len(body), 'records': len(rows)})
        for row in rows:
            require(type(row.get('id')) is int and row['id'] not in seen, 'duplicate Iowa report id')
            seen.add(row['id'])
            reported_day = date.fromisoformat(row['date'][:10])
            require(reported_day <= day and (previous_date is None or reported_day <= previous_date),
                    'Iowa report ordering/date changed')
            previous_date = reported_day
            if reported_day.year < 2026:
                boundary = True
                break
            require(row['reportType'] in ('Organization Independent Expenditure',
                                         'Individual Independent Expenditure'), 'Iowa report type changed')
            require(row['filingStatus'] in ('Certified', 'Adjusted'), 'Iowa unreviewed filing status')
            parsed = urlsplit(row['fileUrl'])
            require(parsed.scheme == 'https' and parsed.netloc == 'iecdbblobstorage.blob.core.windows.net'
                    and parsed.path.startswith('/reports-prod/') and parsed.path.endswith('.pdf')
                    and not parsed.query and not parsed.fragment, 'Iowa report PDF host/path changed')
            file_url = urlunsplit((parsed.scheme, parsed.netloc, quote(parsed.path, safe='/%'), '', ''))
            # Exclude contact details and personal names from the discovery artifact.
            records.append({'report_id': row['id'], 'report_type': row['reportType'],
                            'reported_date': row['date'], 'filed_on': row['filedOn'],
                            'filing_status': row['filingStatus'], 'file_url': file_url,
                            'candidate_mapping': 'PDF_transaction_review_required',
                            'support_cents': None, 'oppose_cents': None})
        if boundary or (page + 1) * PAGE_SIZE >= counts[0]:
            break
    complete = boundary or len(seen) == counts[0]
    return {'schema': 'usa_iowa_ie_report_index_v1', 'state': 'IA', 'cycle': 2026,
            'checked_at': checked_at, 'source_url': API, 'request_kind': 'readonly_public_POST',
            'status': 'report_discovery_complete_mapping_required' if complete else
                      'report_discovery_partial_mapping_required',
            'all_years_report_count': counts[0], 'cycle_reports_observed': len(records),
            'cycle_discovery_complete': complete, 'page_size': PAGE_SIZE, 'max_pages': MAX_PAGES,
            'pagination_strategy': 'single_bounded_page_nonunique_date_sort',
            'candidate_amounts_available': False, 'records': records, 'page_receipts': receipts,
            'limitations_ko': ['공식 공개 목록 발견만 수행. 보고서 수는 거래 수나 후보 금액이 아닙니다.',
                '후보·지지/반대·수정/중복·선거단계는 PDF 거래 검토 전까지 미확보입니다.',
                '최대100건 범위. 수집 상한에 도달하면 전수 확보로 표시하지 않습니다.']}
