"""Recheck explicitly reviewed primary releases absent from the aggregator.

This is a finite reviewed-release list, not automatic admission of new releases.
Failed/changed documents retain the original observation as reference only.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
from html.parser import HTMLParser
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from .polls import require
from .poll_quality import answer_correction_fingerprint
from .state_inputs import primary_document_approved
from .poll_html_evidence import FORMAT as HTML_REGION_FORMAT, html_region_fingerprint

# Reviewed publishers with finite release URLs and SHA-256 snapshots below.
# New releases still require a committed record/document review.
PRIMARY_PDF_HOSTS = frozenset(('poll.qu.edu', 'www.commoncause.org', 'www.nrcc.org', 'www.suffolk.edu', 'static1.squarespace.com', 'law.marquette.edu', 'dccc.org', 's3.documentcloud.org', 'www.ppic.org'))

# Finite poll files on shared CDNs; never approve the whole storage host.
PRIMARY_PDF_RELEASES = frozenset((
    'https://d3nkl3psvxxpe9.cloudfront.net/documents/ttw_nh_20260921_lv.pdf',
    'https://www.insidernj.com/wp-content/uploads/2026/09/StimSight_NJ07_toplines.pdf',
    'https://alabamapolicy.org/wp-content/uploads/2026/10/0926-SURVEY-DATA.pdf',
    'https://yeseverykidfoundation.org/wp-content/uploads/YESF_Alabama-Statewide-Survey_Topline.pdf',
    'https://www.sacredheart.edu/media/shu-media/press-room-2026/SHU-CT-Gubernatorial-Race-Poll-2-of-3-2026-ADA.pdf',
    'https://newspack-coloradosun.s3.amazonaws.com/wp-content/uploads/2026/07/CO-05-Polling-Memo-F07.24.26.pdf',
    'https://cdn.prod.website-files.com/6943653ee8791a8a352e27f7/6aadecdc9101b1b52f7aeec1_CO-08%20Toplines%20(9%3A17).pdf',
))

PRIMARY_XLSX_HOSTS = frozenset(('7453540.fs1.hubspotusercontent-na1.net',))


# Only this reviewed release can use an HTML document. Site navigation and
# recommendations change independently of the poll and are not evidence.
PRIMARY_HTML_RELEASES = frozenset((
    'https://ivn.us/new-ca-poll-voter-id-measure-leads-today-its-undecided-voters-point-the-other-way/',
))

# ASP.NET reports expose their evidence in a main frame. Hash visible text,
# not generated view-state attributes, and admit only the reviewed report.
PRIMARY_SURVEYUSA_RELEASES = {
    'https://results.surveyusa.com/client/PollReport_main.aspx?g=6e6ded19-6ad8-4379-8fa9-6a15dfa99052': '28031',
}


def surveyusa_html_fingerprint(body, report_id):
    class EvidenceText(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []; self.ignored = 0
        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style'): self.ignored += 1
        def handle_endtag(self, tag):
            if tag in ('script', 'style'): self.ignored = max(0, self.ignored - 1)
        def handle_data(self, data):
            if not self.ignored: self.parts.append(data)
    parser = EvidenceText(); parser.feed(body.decode('utf-8')); parser.close()
    canonical = ' '.join(' '.join(parser.parts).split())
    require(f'Results of SurveyUSA Election Poll #{report_id}' in canonical
            and 'About the Research / Filtering:' in canonical
            and len(canonical) > 1000, 'primary SurveyUSA report missing/changed')
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def primary_html_fingerprint(body):
    text = body.decode('utf-8')
    articles = re.findall(r'<article\b([^>]*)>(.*?)</article>', text, re.S | re.I)
    selected = []
    for attrs, content in articles:
        match = re.search(r'''\bclass\s*=\s*["']([^"']*)["']''', attrs, re.I)
        if match and 'ghost-content' in match[1].split():
            selected.append(content)
    require(len(selected) == 1, 'primary HTML evidence article missing/ambiguous')
    class EvidenceText(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []; self.ignored = 0
        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style'): self.ignored += 1
        def handle_endtag(self, tag):
            if tag in ('script', 'style'): self.ignored = max(0, self.ignored - 1)
        def handle_data(self, data):
            if not self.ignored: self.parts.append(data)
    parser = EvidenceText(); parser.feed(selected[0]); parser.close()
    canonical = ' '.join(' '.join(parser.parts).split())
    require(len(canonical) > 100, 'primary HTML evidence article empty')
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def merge_primary_supplements(rows, snapshot, as_of, states=None, opener=urlopen, reviewed_entries=(), isolate_conflicts=False):
    require(snapshot['schema']=='usa_reviewed_primary_poll_supplements_v1'
            and snapshot['cycle']==2026, 'primary supplement schema/cycle')
    output=deepcopy(rows);receipts=[];seen=set()
    for entry in snapshot['records']:
        if states is not None and entry['state'] not in states:continue
        raw=deepcopy(entry['record'])
        require(raw['id'] not in seen and raw['id'].startswith('primary-'), 'duplicate/unreviewed primary ID')
        seen.add(raw['id'])
        require(date.fromisoformat(entry['reviewed_on'])<=date.fromisoformat(as_of)
                and entry['record_sha256']==answer_correction_fingerprint(raw), 'primary supplement snapshot changed')
        documents=entry['documents'];require(documents, 'missing reviewed primary documents')
        for document in documents:
            parsed=urlparse(document['url'])
            state_review = primary_document_approved(entry, document) or entry in reviewed_entries
            require(parsed.scheme=='https' and not parsed.username and not parsed.password
                    and (parsed.hostname in PRIMARY_PDF_HOSTS and parsed.path.endswith('.pdf')
                         or document['url'] in PRIMARY_PDF_RELEASES
                         or parsed.hostname in PRIMARY_XLSX_HOSTS and parsed.path.endswith('.xlsx')
                         or document.get('format') == 'reviewed_html_article_v1'
                            and document['url'] in PRIMARY_HTML_RELEASES
                         or document.get('format') == 'reviewed_surveyusa_report_v1'
                            and document['url'] in PRIMARY_SURVEYUSA_RELEASES
                         or state_review and (parsed.path.endswith(('.pdf','.xlsx'))
                            or document.get('format') in (HTML_REGION_FORMAT, 'reviewed_html_document_v1')
                            or document.get('format') == 'reviewed_pdf_v1'
                            or document.get('format') == 'reviewed_html_article_v1'
                            or document.get('format') == 'reviewed_surveyusa_report_v1'
                                and str(document.get('report_id','')).isdigit()))
                    and len(document['sha256'])==64, 'unreviewed primary document')
        # Replace a verified provider typo only for the exact reviewed snapshot.
        # Changed records still undergo the standard same-wave conflict check.
        replaced=[]
        for replacement in entry.get('reviewed_provider_replacements', []):
            require(replacement['reason']=='candidate_name_typo'
                    and replacement['id']!=raw['id']
                    and len(replacement['provider_snapshot_sha256'])==64,
                    'unreviewed_provider_replacement')
            matching=[r for r in output if r.get('id')==replacement['id']
                      and answer_correction_fingerprint(r)==replacement['provider_snapshot_sha256']]
            output=[r for r in output if r not in matching]
            replaced.extend(r['id'] for r in matching)
        # A later API import of this same wave must agree before deduplication.
        keys=('subject','poll_type','pollster','start_date','end_date','population')
        duplicates=[r for r in output if all(r.get(k)==raw.get(k) for k in keys)]
        # Exact-reviewed questions from one wave remain distinct. An ordinary
        # initial pair may differ from the full ballot; this transport exception
        # never relaxes normalize's full-field or signal-eligibility checks.
        separate = entry.get('same_wave_separate_question_reviews', [])
        for question in separate:
            require(question['reason'] in ('different_ranked_choice_question',
                                          'different_initial_ballot_question')
                    and question['question'] and question['id'] != raw['id']
                    and len(question['provider_snapshot_sha256']) == 64,
                    'unreviewed_same_wave_question')
            if question['reason'] == 'different_initial_ballot_question':
                require(question.get('primary_record_sha256') == entry['record_sha256']
                        and question.get('primary_question')
                        and question['primary_question'] != question['question']
                        and question.get('wave_id')
                        and question.get('reviewed_on')
                        and date.fromisoformat(question['reviewed_on']) <= date.fromisoformat(as_of)
                        and question.get('primary_ballot_format') == 'initial_named_multicandidate'
                        and question.get('provider_ballot_format') == 'initial_named_two_candidate'
                        and question.get('source_document') in documents,
                        'unreviewed_initial_ballot_question_scope')
        distinct = [r for r in duplicates if any(r['id'] == q['id']
            and answer_correction_fingerprint(r) == q['provider_snapshot_sha256'] for q in separate)]
        for r in distinct:
            if any(q['reason'] == 'different_initial_ballot_question' and q['id'] == r['id'] for q in separate):
                names = lambda row: {a['choice'] for a in row['answers']}
                require(len(r['answers']) == len(names(r)) == 2
                        and len(raw['answers']) == len(names(raw)) >= 3
                        and names(r) < names(raw), 'initial_ballot_candidate_scope_mismatch')
        duplicates = [r for r in duplicates if r not in distinct]
        values=lambda r:sorted((a['choice'],a['pct']) for a in r['answers'])
        conflict = not all(r['sample_size']==raw['sample_size'] and values(r)==values(raw)
                    and r.get('internal')==raw.get('internal') and r.get('partisan')==raw.get('partisan')
                    and (r.get('sponsors') or [])==(raw.get('sponsors') or []) for r in duplicates)
        require(not conflict or isolate_conflicts, 'primary_and_provider_wave_conflict')
        checks=[]
        for document in documents:
            try:
                with opener(Request(document['url'],headers={'User-Agent':'ElectionWatch/1.0 primary-release-review'}),timeout=25) as response:
                    require(response.status==200 and response.geturl()==document['url'], 'primary document redirect/response')
                    body=response.read(3*1024*1024+1)
                require(len(body)<=3*1024*1024, 'primary document size changed')
                if document.get('format') == 'reviewed_html_document_v1':
                    require(body.lstrip().lower().startswith((b'<!doctype html', b'<html', b'<nav')), 'primary HTML document format changed')
                    digest = hashlib.sha256(body).hexdigest()
                elif document.get('format') == HTML_REGION_FORMAT:
                    digest = html_region_fingerprint(body, document)
                elif document.get('format') == 'reviewed_html_article_v1':
                    digest = primary_html_fingerprint(body)
                elif document.get('format') == 'reviewed_surveyusa_report_v1':
                    digest = surveyusa_html_fingerprint(body, str(document.get('report_id') or PRIMARY_SURVEYUSA_RELEASES[document['url']]))
                else:
                    require(body.startswith(b'%PDF-') if (urlparse(document['url']).path.endswith('.pdf') or document.get('format') == 'reviewed_pdf_v1') else body.startswith(b'PK\x03\x04'), 'primary document format changed')
                    digest=hashlib.sha256(body).hexdigest()
                checks.append({'url':document['url'],'status':'unchanged' if digest==document['sha256'] else 'changed_review_required',
                               'sha256':digest})
            except (OSError,ValueError) as error:
                checks.append({'url':document['url'],'status':'unavailable','error_type':type(error).__name__})
        current=all(c['status']=='unchanged' for c in checks)
        capture={'status':('primary_provider_conflict_reference_only' if conflict else
                    'primary_documents_rechecked' if current else 'carried_forward_reference_only'),
                 'original_reviewed_on':entry['reviewed_on'],'checked_at':datetime.now(timezone.utc).isoformat(),
                 'documents':checks,'provider_duplicate_ids':[r['id'] for r in duplicates],
                 'reviewed_replaced_provider_ids':replaced,
                 'separate_question_provider_ids':[r['id'] for r in distinct]}
        if conflict:
            capture['conflict_reason']='primary_and_provider_wave_conflict'
            capture['conflicting_provider_records']=deepcopy(duplicates)
        raw['primary_source_capture']=capture
        output=[r for r in output if r not in duplicates];output.append(raw)
        receipts.append({'id':raw['id'],'state':entry['state'],**capture})
    return output,receipts


def _network_only(failures):
    """Failures that only say a page could not be fetched (no evidence it changed)."""
    return bool(failures) and all(f.get('error_type') and 'id' not in f for f in failures)


def keep_unreachable_primary_receipts(previous_capture, receipts, records):
    """Offline packet replay must not erase an earlier successful recheck.

    When every publisher document of a reviewed release is merely unreachable
    (no body fetched, so no evidence it changed), keep the previous packet's
    receipt and primary record for that ID. The same holds for reviewed HTML
    tables (kind html_table) whose page could not be fetched, and for their
    table health line. A record that dropped out of the replay while its
    receipt is kept is put back in the previous packet's order. A changed
    digest, a different document set, a changed same-wave table row or a new
    review date is real news and is never masked. Returns (receipts, records, kept_ids).
    """
    previous_capture = previous_capture or {}
    prev_list = (previous_capture.get('receipt') or {}).get('primary_supplement_receipts', [])
    old_receipts = {r.get('id'): r for r in prev_list if r.get('id')}
    old_health = {r.get('contract_id'): r for r in prev_list if r.get('kind') == 'html_table_health'}
    prev_records = previous_capture.get('primary_records', [])
    old_records = {r.get('id'): r for r in prev_records}
    kept = set()
    out = []
    for receipt in receipts:
        prev = old_receipts.get(receipt.get('id'))
        docs = receipt.get('documents') or []
        if receipt.get('kind') == 'html_table':
            ok = (prev and prev.get('contract_sha256') == receipt.get('contract_sha256')
                  and receipt['record']['primary_source_capture']['status'] == 'carried_forward_reference_only'
                  and prev['record']['primary_source_capture']['status'] != 'carried_forward_reference_only'
                  and _network_only(receipt.get('failures')))
        else:
            ok = (prev and docs and receipt['id'] in old_records
                  and all(d.get('status') == 'unavailable' for d in docs)
                  and prev.get('status') == 'primary_documents_rechecked'
                  and prev.get('original_reviewed_on') == receipt.get('original_reviewed_on')
                  and sorted(d.get('url') for d in prev.get('documents', [])) == sorted(d.get('url') for d in docs))
        if ok:
            out.append(deepcopy(prev))
            kept.add(receipt['id'])
        else:
            out.append(receipt)
    # Table health follows its rows: restore it only when every carried row was kept.
    for i, receipt in enumerate(out):
        prev = old_health.get(receipt.get('contract_id')) if receipt.get('kind') == 'html_table_health' else None
        rows = [r for r in out if r.get('kind') == 'html_table' and r.get('contract_id') == receipt.get('contract_id')]
        if prev and receipt.get('status') == 'partial_last_good_preserved' and _network_only(receipt.get('failures')) \
                and rows and all(r['id'] in kept for r in rows):
            out[i] = deepcopy(prev)
    records = [deepcopy(old_records[r['id']]) if r.get('id') in kept and r['id'] in old_records else r for r in records]
    have = {r.get('id') for r in records}
    for rid in [r['id'] for r in prev_records if r['id'] in kept and r['id'] not in have] + \
               [r['id'] for r in prev_records if r['id'] not in have and old_receipts.get(r['id']) in
                [x for x in out if x.get('id') == r['id']]]:
        if rid in {r.get('id') for r in records}:
            continue
        # Insert just before the record that followed it in the previous packet.
        order = [r['id'] for r in prev_records]
        after = order[order.index(rid) + 1:]
        pos = next((i for i, r in enumerate(records) if r.get('id') in after), len(records))
        records.insert(pos, deepcopy(old_records[rid]))
    return out, records, kept
