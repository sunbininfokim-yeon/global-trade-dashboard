"""Recheck explicitly reviewed primary releases absent from the aggregator.

This is a finite reviewed-release list, not automatic admission of new releases.
Failed/changed documents retain the original observation as reference only.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from .polls import require
from .poll_quality import answer_correction_fingerprint

# Reviewed publishers with finite release URLs and SHA-256 snapshots below.
# New releases still require a committed record/document review.
PRIMARY_PDF_HOSTS = frozenset(('poll.qu.edu', 'www.commoncause.org', 'www.nrcc.org', 'www.suffolk.edu', 'static1.squarespace.com', 'law.marquette.edu', 'dccc.org', 's3.documentcloud.org'))

PRIMARY_XLSX_HOSTS = frozenset(('7453540.fs1.hubspotusercontent-na1.net',))

def merge_primary_supplements(rows, snapshot, as_of, states=None, opener=urlopen):
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
            require(parsed.scheme=='https' and not parsed.username and not parsed.password
                    and (parsed.hostname in PRIMARY_PDF_HOSTS and parsed.path.endswith('.pdf')
                         or parsed.hostname in PRIMARY_XLSX_HOSTS and parsed.path.endswith('.xlsx'))
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
        values=lambda r:sorted((a['choice'],a['pct']) for a in r['answers'])
        require(all(r['sample_size']==raw['sample_size'] and values(r)==values(raw)
                    and r.get('internal')==raw.get('internal') and r.get('partisan')==raw.get('partisan')
                    and (r.get('sponsors') or [])==(raw.get('sponsors') or []) for r in duplicates),
                'primary_and_provider_wave_conflict')
        checks=[]
        for document in documents:
            try:
                with opener(Request(document['url'],headers={'User-Agent':'ElectionWatch/1.0 primary-release-review'}),timeout=25) as response:
                    require(response.status==200 and response.geturl()==document['url'], 'primary document redirect/response')
                    body=response.read(3*1024*1024+1)
                require(len(body)<=3*1024*1024 and (body.startswith(b'%PDF-') if urlparse(document['url']).path.endswith('.pdf') else body.startswith(b'PK\x03\x04')), 'primary document format/size changed')
                digest=hashlib.sha256(body).hexdigest()
                checks.append({'url':document['url'],'status':'unchanged' if digest==document['sha256'] else 'changed_review_required',
                               'sha256':digest})
            except (OSError,ValueError) as error:
                checks.append({'url':document['url'],'status':'unavailable','error_type':type(error).__name__})
        current=all(c['status']=='unchanged' for c in checks)
        capture={'status':'primary_documents_rechecked' if current else 'carried_forward_reference_only',
                 'original_reviewed_on':entry['reviewed_on'],'checked_at':datetime.now(timezone.utc).isoformat(),
                 'documents':checks,'provider_duplicate_ids':[r['id'] for r in duplicates],
                 'reviewed_replaced_provider_ids':replaced}
        raw['primary_source_capture']=capture
        output=[r for r in output if r not in duplicates];output.append(raw)
        receipts.append({'id':raw['id'],'state':entry['state'],**capture})
    return output,receipts
