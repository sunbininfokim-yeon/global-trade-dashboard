#!/usr/bin/env python3
"""Bounded all-source backfill + refresh, with transactionally committed DB cursors."""
import argparse
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

sys.path.insert(0, str(Path(__file__).parent))
from core import VERSION, country_code, digest, fara_record, fara_records, lda_record, policy_refs, read_bulk, tags

BULK = {'registrant': 'Registrants', 'principal': 'ForeignPrincipals',
        'person': 'ShortForms', 'document': 'RegistrantDocs'}
LDA = 'https://lda.gov/api/v1/filings/'


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlparse(req.full_url), urlparse(newurl)
        allowed = {'lda.gov', 'lda.senate.gov'} if old.hostname in {'lda.gov', 'lda.senate.gov'} else {old.hostname}
        if new.scheme != 'https' or new.hostname not in allowed or new.username or new.password:
            raise ValueError('Unexpected source redirect; authorization not forwarded')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Http:
    def __init__(self):
        self.next_source_at = 0

    def get(self, url, headers=None, limit=60_000_000, source=True):
        if source:
            time.sleep(max(0, self.next_source_at - time.monotonic()))
            self.next_source_at = time.monotonic() + 4.5  # safe anonymous LDA and FARA pacing
        for attempt in range(4):
            try:
                req = Request(url, headers={'User-Agent': 'ChokeMonitor-Lobbying/1.0', **(headers or {})})
                with build_opener(OfficialRedirects()).open(req, timeout=45) as response:
                    data = response.read(limit+1)
                    if len(data) > limit:
                        raise ValueError('Source response exceeds bounded download limit')
                    return data
            except HTTPError as error:
                if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 3:
                    raise RuntimeError(f'Source HTTP {error.code}; cursor preserved') from None
                delay = error.headers.get('Retry-After', '')
                time.sleep(min(60, float(delay) if delay.isdigit() else 2**attempt * 3))
        raise RuntimeError('Source fetch failed')


class Database:
    def __init__(self):
        self.base = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/'
        key = os.environ['SUPABASE_SERVICE_ROLE_KEY']
        self.headers = {'apikey': key, 'Content-Type': 'application/json'}
        if key.startswith('eyJ'):
            self.headers['Authorization'] = 'Bearer ' + key

    def request(self, path, body=None):
        req = Request(self.base+path, data=json.dumps(body).encode() if body is not None else None,
                      headers=self.headers, method='POST' if body is not None else 'GET')
        try:
            with urlopen(req, timeout=90) as response:
                data = response.read(8_000_000)
                return json.loads(data) if data else None
        except HTTPError as error:
            # Never print response bodies that might contain database values or credentials.
            raise RuntimeError(f'Database HTTP {error.code}') from None

    def rpc(self, name, **kwargs):
        return self.request('rpc/'+name, kwargs)


def next_lda_url(value):
    if value is None:
        return None
    p = urlparse(value)
    if p.scheme != 'https' or p.hostname not in {'lda.gov', 'lda.senate.gov'} or p.path != '/api/v1/filings/' or p.username or p.password:
        raise ValueError('Unsafe LDA pagination URL; credentials not forwarded')
    return value


def commit(db, stream, owner, records, cursor, expected=None, complete=False):
    return db.rpc('lobby_commit_batch', p_stream=stream, p_owner=owner, p_records=records,
                  p_cursor=cursor, p_expected=expected, p_complete=complete)


def run_stream(db, name, work):
    owner = str(uuid.uuid4())
    state = db.rpc('lobby_claim_stream', p_stream=name, p_owner=owner)
    if state is None:
        return {'stream': name, 'status': 'leased_elsewhere'}
    try:
        size = db.rpc('lobby_database_bytes')
        budget = int(os.environ.get('LOBBYING_DB_BUDGET_BYTES', 6*1024**3))
        if isinstance(size, int) and size > budget:
            raise RuntimeError('Storage budget reached; ingestion held with cursor preserved')
        result = work(owner, state or {})
        db.rpc('lobby_finish_stream', p_stream=name, p_owner=owner, p_error=None)
        return {'stream': name, **result}
    except Exception as error:
        message = f'{type(error).__name__}: {str(error)[:200]}'
        db.rpc('lobby_finish_stream', p_stream=name, p_owner=owner, p_error=message)
        return {'stream': name, 'status': 'source_unavailable', 'error': message}


def fara_sync(db, http, cache, batches, batch_size):
    snapshots = {}
    for kind, name in BULK.items():
        url = f'https://efile.fara.gov/bulk/zip/FARA_All_{name}.csv.zip'
        path = cache / f'FARA_All_{name}.csv.zip'
        data = http.get(url)
        path.write_bytes(data)
        rows = read_bulk(data)
        if not rows or 'Registration Number' not in rows[0]:
            raise ValueError('FARA bulk schema/empty response; previous inventory preserved')
        snapshots[kind] = (rows, digest(data))
    countries = {}
    for row in snapshots['principal'][0]:
        if row.get('_source_parse_status'):
            continue
        c = country_code(row.get('Country/Location Represented'))
        if c:
            countries.setdefault(row['Registration Number'], set()).add(c)
    results = []
    for kind, (rows, sha) in snapshots.items():
        # Stable IDs protect the historical cursor from daily insertions/reordering.
        ordered = fara_records(rows, kind, countries)

        def work(owner, state, kind=kind, ordered=ordered, sha=sha):
            stream = 'fara:' + kind
            cursor = state.get('cursor') or {}
            after = cursor.get('after', '')
            remaining = [row for row in ordered if row['record_id'] > after]
            if not remaining:
                remaining = ordered
                cursor = {**cursor, 'after': ''}
            processed = 0
            # Refresh newest documents independently of a historical position. No country/sector filter.
            if kind == 'document':
                recent = sorted(ordered, key=lambda row: row['source_date'] or '', reverse=True)[:batch_size]
                commit(db, stream, owner, recent, cursor, len(ordered))
            for offset in range(0, min(len(remaining), batches*batch_size), batch_size):
                batch = remaining[offset:offset+batch_size]
                done = offset+len(batch) >= len(remaining)
                cursor = {'after': '' if done else batch[-1]['record_id'], 'snapshot_sha256': sha,
                          'completed_passes': int(cursor.get('completed_passes', 0)) + int(done)}
                commit(db, stream, owner, batch, cursor, len(ordered), done)
                processed += len(batch)
            return {'status': 'complete_pass' if cursor.get('after') == '' else 'partial', 'processed': processed,
                    'expected': len(ordered), 'snapshot_sha256': sha}
        results.append(run_stream(db, 'fara:'+kind, work))
    return results


def lda_sync(db, http, pages):
    token = os.environ.get('LDA_API_KEY')
    headers = {'Authorization': 'Token '+token} if token else {}
    results = []
    # Refresh starts from the official default listing each run. Backfill follows
    # official next links; it has no country/client/industry/date restriction.
    for lane, budget in [('refresh', 2), ('backfill', pages)]:
        stream = 'lda:'+lane

        def work(owner, state, lane=lane, budget=budget, stream=stream):
            cursor = state.get('cursor') or {}
            url = LDA if lane == 'refresh' else next_lda_url(cursor.get('next') or LDA)
            processed = 0
            for _ in range(budget):
                page = json.loads(http.get(url, headers=headers, limit=15_000_000))
                if not isinstance(page, dict) or not isinstance(page.get('results'), list) or not isinstance(page.get('count'), int) or 'next' not in page:
                    raise ValueError('LDA listing schema not recognized; cursor held')
                rows = [lda_record(row) for row in page['results']]
                nxt = next_lda_url(page['next'])
                cursor = {'next': nxt, 'completed_passes': int(cursor.get('completed_passes', 0)) + int(nxt is None)}
                commit(db, stream, owner, rows, cursor, page['count'], nxt is None)
                processed += len(rows)
                if nxt is None:
                    break
                url = nxt
            return {'status': 'complete_pass' if cursor.get('next') is None else 'partial', 'processed': processed}
        results.append(run_stream(db, stream, work))
    return results


def extract_pdf(data, cache):
    if not data.startswith(b'%PDF-'):
        raise ValueError('Source is not a PDF')
    sha = digest(data)
    pdf = cache / (sha+'.pdf')
    txt = cache / (sha+'.txt')
    pdf.write_bytes(data)
    if shutil.which('pdftotext'):
        subprocess.run(['pdftotext', '-layout', str(pdf), str(txt)], check=True, timeout=60, capture_output=True)
        pages = txt.read_text(errors='replace').split('\f')
    else:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > 500:
            raise ValueError('PDF page budget exceeded; held for separate extraction')
        pages = []
        for page in reader.pages:
            content = page.get_contents()
            if content is not None and len(content.get_data()) > 10_000_000:
                raise ValueError('PDF page stream budget exceeded')
            pages.append(page.extract_text() or '')
    if sum(len(p) for p in pages) > 2_000_000:
        raise ValueError('Extracted text budget exceeded; held for separate extraction')
    if sum(len(p.strip()) for p in pages) < 100:
        return {'text_state': 'ocr_required', 'body_sha256': sha, 'pages': []}
    return {'text_state': 'extracted', 'body_sha256': sha,
            'pages': [{'page': i+1, 'text': p} for i, p in enumerate(pages) if p.strip()],
            'body_text': '\n\n'.join(pages)}


def text_sync(db, http, cache, count):
    def work(owner, state):
        rows = db.request('lobby_records?'+urlencode({'select': 'record_id,source_url,raw_payload,payload_hash',
                          'source': 'eq.fara', 'kind': 'eq.document',
                          'source_url': 'like.https://efile.fara.gov/docs/*',
                          'text_state': 'in.(pending,source_unavailable)', 'order': 'last_text_attempt.asc.nullsfirst,source_date.desc.nullslast', 'limit': str(count)}))
        processed = 0
        failed = 0
        for row in rows:
            try:
                result = extract_pdf(http.get(row['source_url']), cache)
                references = []
                for page in result.get('pages', []):
                    references.extend(policy_refs(page['text'], {'page': page['page']}))
                row.update(result, references=references, topics=tags(result.get('body_text', '')))
            except Exception as error:
                row.update(text_state='source_unavailable', text_error=type(error).__name__+': '+str(error)[:150])
                failed += 1
            commit(db, 'fara:text', owner, [row], {'last_record': row['record_id']})
            processed += 1
        return {'status': 'partial', 'processed': processed, 'failed_count': failed}
    return [run_stream(db, 'fara:text', work)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', choices=['all', 'fara', 'lda', 'text'], default='all')
    p.add_argument('--batches', type=int, default=8)
    p.add_argument('--batch-size', type=int, default=250)
    p.add_argument('--pages', type=int, default=20)
    p.add_argument('--pdfs', type=int, default=10)
    p.add_argument('--cache-dir', required=True)
    args = p.parse_args()
    if not (1 <= args.batches <= 100 and 1 <= args.batch_size <= 500 and 1 <= args.pages <= 200 and 0 <= args.pdfs <= 100):
        p.error('Batch bounds exceeded')
    # A feature branch never writes production via Actions. Local manual writes
    # require the operator to choose a sink explicitly by supplying both secrets.
    if os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise SystemExit('Production collection is main-only')
    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    db, http = Database(), Http()
    output = []
    if args.source in ('all', 'fara'):
        try:
            output.extend(fara_sync(db, http, cache, args.batches, args.batch_size))
        except Exception as error:
            # Inventory fetch precedes per-kind leases: record the failed source too.
            def failed(_owner, _state):
                raise error
            output.append(run_stream(db, 'fara:inventory', failed))
    if args.source in ('all', 'lda'):
        output.extend(lda_sync(db, http, args.pages))
    if args.source in ('all', 'text') and args.pdfs:
        output.extend(text_sync(db, http, cache, args.pdfs))
    db.rpc('lobby_resolve_policy_links', p_limit=1000)
    result = {'version': VERSION, 'scope': 'all_countries_all_industries_all_available_history', 'streams': output}
    (cache/'run.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))
    return int(any(row.get('status') == 'source_unavailable' or row.get('failed_count',0) for row in output))


if __name__ == '__main__':
    sys.exit(main())
