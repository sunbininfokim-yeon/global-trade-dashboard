"""Discover Kansas official scanned IE reports; monetary normalization is held.

The index mixes candidate and constitutional-ballot spending. A report period
is not an election stage or a filing date. PAC S/O means organization, not
support/oppose. No amount is inferred from a committee name or PDF filename.
"""
from datetime import date, datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .superpac import SourceError
from .polls import require

IE_INDEX = 'https://www.kansas.gov/ethics/CFAScanned/Others/2026ElecCycle/IndependentExpendLink.htm'
PAC_INDEX = 'https://www.kansas.gov/ethics/CFAScanned/PACs/2026ElecCycle/PAC%20Links2026EC.htm'
PORTAL = 'https://kpdc.kansas.gov/campaign-finance/view-submitted-forms-and-reports/'


class _Index(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []; self.row = None; self.cell = None; self.link = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            # HTML permits an omitted </td>; the current ACF row uses it.
            self._finish_cell()
            self.cell = {'text': [], 'links': []}
        elif tag == 'a' and self.cell is not None:
            self.link = {'href': dict(attrs).get('href', ''), 'text': []}

    def handle_data(self, text):
        if self.cell is not None:
            self.cell['text'].append(text)
        if self.link is not None:
            self.link['text'].append(text)

    def handle_endtag(self, tag):
        if tag == 'a' and self.link is not None:
            self.link['text'] = ' '.join(' '.join(self.link['text']).split())
            self.cell['links'].append(self.link); self.link = None
        elif tag in ('td', 'th') and self.cell is not None:
            self._finish_cell()
        elif tag == 'tr' and self.row is not None:
            self._finish_cell()
            self.rows.append(self.row); self.row = None

    def _finish_cell(self):
        if self.cell is not None:
            if self.link is not None:
                raise SourceError('Kansas unclosed report link')
            self.cell['text'] = ' '.join(' '.join(self.cell['text']).split())
            self.row.append(self.cell); self.cell = None


def _page(raw, expected, as_of):
    try:
        html = raw.decode('cp1252')
    except UnicodeError:
        raise SourceError('Kansas index encoding changed') from None
    text = ' '.join(unescape(re.sub('<[^>]+>', ' ', html)).split())
    if expected not in text or not re.search(r'2026\s+Election Cycle', text):
        raise SourceError('Kansas report index title/cycle changed')
    updated = re.search(r'Last Updated:\s*([A-Za-z]+ \d{1,2}, 2026)', text)
    if not updated:
        raise SourceError('Kansas report index date unavailable')
    day = datetime.strptime(updated[1], '%B %d, %Y').date()
    if day > date.fromisoformat(as_of):
        raise SourceError('Kansas index update is in the future')
    parser = _Index(); parser.feed(html)
    if (not parser.rows or parser.row is not None or parser.cell is not None
            or not re.search(r'</table\s*>', html, re.I)):
        raise SourceError('Kansas report table unavailable')
    return parser.rows, day.isoformat(), html


def parse_ie_index(raw, as_of):
    rows, updated, _ = _page(raw, 'INDEPENDENT EXPENDITURES', as_of)
    header = rows[0]
    if len(header) != 5 or header[0]['text'] != 'Committee Name' or not all(
            code in header[i]['text'] for i, code in enumerate(('202601','202607','202610','202701'), 1)):
        raise SourceError('Kansas IE report columns changed')
    reports = []; seen = set(); committees = set()
    for row in rows[1:]:
        if row and all(not c['text'] and not c['links'] for c in row):
            continue
        if len(row) != 5 or not row[0]['text'] or row[0]['links']:
            raise SourceError('Kansas IE committee row changed')
        committee = row[0]['text']
        if committee in committees:
            raise SourceError('Kansas duplicate committee row')
        committees.add(committee)
        for i, period in enumerate(('202601','202607','202610','202701'), 1):
            for link in row[i]['links']:
                url = urljoin(IE_INDEX, link['href']); parsed = urlparse(url)
                if (parsed.scheme != 'https' or parsed.netloc != 'www.kansas.gov'
                        or not parsed.path.startswith('/ethics/CFAScanned/Others/2026ElecCycle/')
                        or not parsed.path.lower().endswith('.pdf') or parsed.query or parsed.fragment
                        or '..' in parsed.path.split('/') or link['text'] != period or url in seen):
                    raise SourceError('Kansas IE report URL/period/identity changed')
                seen.add(url)
                reports.append({'committee': committee, 'report_url': url, 'reported_period_label': period,
                    'filing_date': None, 'election_stage': 'unknown', 'target_type': 'not_reviewed',
                    'candidate_amounts_available': False, 'normalization_status': 'PDF_target_direction_and_amendment_review_required'})
    if not reports or len(reports) > 2000:
        raise SourceError('Kansas empty/oversized IE report index')
    return {'source_url': IE_INDEX, 'source_updated_on': updated, 'sha256': sha256(raw).hexdigest(),
        'indexed_committees': len(committees), 'indexed_report_links': len(reports), 'reports': reports}


def summarize_indices(ie_raw, pac_raw, cycle, roster, captured_at):
    if cycle != 2026 or not roster or any(c['state'] != 'KS' or c['office'] != 'G' for c in roster):
        raise SourceError('Kansas requires reviewed 2026 governor candidates')
    ie = parse_ie_index(ie_raw, captured_at[:10])
    _, pac_day, pac_html = _page(pac_raw, 'Political Action Committees', captured_at[:10])
    if 'Statement of Organization' not in ' '.join(unescape(re.sub('<[^>]+>', ' ', pac_html)).split()):
        raise SourceError('Kansas PAC organization legend changed')
    return {'schema': 'usa_governor_finance_audit_v1', 'state': 'KS', 'cycle': cycle,
        'captured_at': captured_at, 'status': 'collected_normalization_held', 'source_url': PORTAL,
        'collection_scope': 'public_report_indices_only', 'financial_data_collected': False,
        'sources': [ie, {'source_url': PAC_INDEX, 'source_updated_on': pac_day,
                        'sha256': sha256(pac_raw).hexdigest(), 'scope': 'PAC_index_access_and_legend_only'}],
        'input_records': ie['indexed_report_links'], 'input_record_unit': 'report_link_not_transaction',
        'current_governor_target_records': None, 'candidate_amounts_available': False,
        'cycle_discovery_complete': False, 'report_PDFs_parsed_by_collector': 0,
        'candidate_audits': [{'candidate_id': c['candidate_id'], 'name': c['name'], 'party': c['party'],
            'reported_target': None, 'reported_rows': None, 'support_cents': None, 'oppose_cents': None,
            'amount_status': 'PDF_target_direction_and_amendment_review_required'} for c in roster],
        'hold_reasons': ['candidate_and_constitutional_ballot_reports_mixed', 'PDF_transaction_extraction_not_implemented',
                         'PAC_contributions_and_independent_expenditure_not_joined', 'amendment_lineage_not_verified'],
        'limitations_ko': ['공식 IE 보고서 목록을 자동 재수집합니다. PDF 거래·후보별 금액 수집은 아직 미구현입니다.',
            '목록은 후보와 주민투표 공시를 포함하며 PAC 보고서와 별도입니다. PAC의 S/O는 조직신고서로 지지·반대가 아닙니다.',
            '보고기간 코드202610은 신고일·본선 지출 판정이 아닙니다. 후보 이름·선거·지지반대·정정 관계 확인 전 금액은null입니다.',
            '목록의 Last Updated를 원래 그대로 보존하며 현재 수집일이나 최신 후보 독립지출일로 바꾸지 않습니다.']}


def recheck_document_references(reviews, roster, index, captured_at, fetch):
    """Recheck a finite human-reviewed PDF set, never turn it into a total."""
    require(reviews['schema'] == 'usa_ks_governor_ie_document_reviews_v1'
            and reviews['state'] == 'KS' and reviews['cycle'] == 2026,
            'Kansas document review scope changed')
    candidates = {c['candidate_id']: c for c in roster}
    indexed = {r['report_url']: r for r in index['reports']}
    result = []; seen = set()
    for review in reviews['documents']:
        url = review['url']; parsed = urlparse(url)
        require(parsed.scheme == 'https' and parsed.netloc == 'www.kansas.gov'
                and parsed.path.startswith('/ethics/CFAScanned/Others/2026ElecCycle/')
                and parsed.path.endswith('.pdf') and not parsed.query and not parsed.fragment
                and url not in seen and re.fullmatch('[0-9a-f]{64}', review['sha256']) is not None,
                'Kansas unreviewed PDF identity')
        seen.add(url)
        require(date.fromisoformat(review['checked_at'][:10]) <= date.fromisoformat(captured_at[:10])
                and review['visual_review_complete'] is True, 'Kansas future/unreviewed PDF')
        for row in review['rows']:
            candidate = candidates.get(row['candidate_id'])
            require(candidate and candidate['name'] == row['candidate_name']
                    and row['office'] == 'governor' and row['direction'] in ('support', 'oppose')
                    and type(row['amount_cents']) is int and row['amount_cents'] > 0
                    and row['election_stage'] == 'pre_nomination_reference'
                    and date.fromisoformat(row['expenditure_date']) < date(2026, 8, 4),
                    'Kansas reviewed reference row changed')
        receipt = {'reviewed_document': review, 'checked_at': captured_at,
                   'aggregation_eligible': False, 'election_result': False}
        if url not in indexed:
            receipt['status'] = 'carried_forward_reference_source_link_missing'
        else:
            try:
                body = fetch(url)
                if not body.startswith(b'%PDF-') or sha256(body).hexdigest() != review['sha256']:
                    receipt['status'] = 'carried_forward_reference_document_changed'
                else:
                    receipt['status'] = 'reviewed_reference_document_unchanged'
                receipt['current_document_sha256'] = sha256(body).hexdigest()
            except (OSError, SourceError):
                receipt['status'] = 'carried_forward_reference_source_unavailable'
        result.append(receipt)
    return result


def collect_audit(cycle, roster, opener=urlopen, document_reviews=None):
    def fetch(url):
        with opener(Request(url, headers={'User-Agent': 'ElectionWatch/1.0 public-source-review'}), timeout=25) as response:
            if response.status != 200 or response.geturl() != url:
                raise SourceError('Kansas index response/redirect changed')
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise SourceError('Kansas index exceeded size budget')
        return body
    ie_raw = fetch(IE_INDEX)
    pac_raw = fetch(PAC_INDEX)
    captured_at = datetime.now(timezone.utc).isoformat()
    audit = summarize_indices(ie_raw, pac_raw, cycle, roster, captured_at)
    if document_reviews:
        audit['reviewed_PDF_references'] = recheck_document_references(
            document_reviews, roster, audit['sources'][0], captured_at, fetch)
        audit['limitations_ko'].append('특정2개 PDF는 검토 지문을 재확인하는 경선 전 참고입니다. 전체보고 합계·정정관계가 미확정되어 후보별 본선 금액에 합산하지 않습니다.')
    return audit
