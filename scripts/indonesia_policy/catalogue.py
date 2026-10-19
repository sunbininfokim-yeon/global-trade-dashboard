"""Enumerate government catalogues before selecting laws. No PDF/AI/DB calls.

Checkpoints advance only after parse+merge. Completeness is limited to the
registered listing, never the country's legal corpus. Raw responses stay local.
"""
import argparse
import fcntl
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from bs4 import BeautifulSoup
from collect import fetch, normalized, official_url


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def identity(title):
    """Only the leading document heading; never borrow an amendment's target ID."""
    head = re.split(r'\btentang\b', title, maxsplit=1, flags=re.I)[0]
    low = head.lower()
    kind, issuer, level, jurisdiction = None, None, None, None
    for phrase, typ, agency in [
        ('peraturan pemerintah pengganti', 'Perppu', 'national'),
        ('undang-undang', 'UU', 'national'), ('undang undang', 'UU', 'national'),
        ('peraturan pemerintah', 'PP', 'national'), ('peraturan presiden', 'Perpres', 'national'),
        ('instruksi presiden', 'Inpres', 'national'),
        ('peraturan menteri perdagangan', 'Permendag', 'kemendag'),
        ('peraturan menteri perindustrian', 'Permenperin', 'kemenperin'),
        ('peraturan menteri pertanian', 'Permentan', 'pertanian'),
        ('peraturan menteri keuangan', 'PMK', 'kemenkeu'),
        ('peraturan menteri energi', 'Permen', 'esdm'), ('peraturan menteri esdm', 'Permen', 'esdm'),
        ('peraturan daerah', 'Perda', None), ('peraturan gubernur', 'Pergub', None),
        ('peraturan bupati', 'Perbup', None)]:
        if low.startswith(phrase):
            kind, issuer = typ, agency
            level = 'national' if agency else None
            break
    for place in ['Jawa Tengah', 'Sulawesi Barat', 'Kalimantan Timur', 'Sulawesi Tengah']:
        if kind in ('Perda', 'Pergub', 'Perbup') and place.lower() in low:
            jurisdiction, level = place, 'provincial' if kind != 'Perbup' else None
    match = re.search(r'\b(?:nomor|no\.?)\s+([\w./-]+)\s+tahun\s+((?:19|20)\d{2})\b', head, re.I)
    number, year = (match.group(1), int(match.group(2))) if match else (None, None)
    if not match:
        slash = re.search(r'\b(?:nomor|no\.?)\s+([\w./-]+/((?:19|20)\d{2}))\b', head, re.I)
        if slash:
            number, year = slash.group(1), int(slash.group(2))
    return dict(document_type=kind, document_number=number, document_year=year,
                issuer_key=issuer, issuer_level=level, jurisdiction=jurisdiction)


def item(record_id, title, page_url, detail=None, download=None, **extra):
    if not title or not 1 <= len(title) <= 2000:
        raise ValueError('invalid_catalogue_title')
    return dict(source_record_id=str(record_id), title=title, page_url=page_url,
                detail_url=detail if detail and official_url(detail) else None,
                download_url=download if download and official_url(download) else None,
                **identity(title), **extra)


def parse_page(data, url, source):
    adapter = source['adapter']
    records, links, expected = [], [], None
    if adapter == 'ildis_json':
        rows = json.loads(data)
        if not isinstance(rows, list):
            raise ValueError('not_a_document_feed')
        for row in rows:
            if not isinstance(row, dict) or not row.get('idData') or not row.get('judul'):
                raise ValueError('invalid_feed_record')
            records.append(item(row['idData'], normalized(row['judul']), url,
                                row.get('urlDetailPeraturan'), row.get('urlDownload'),
                                publisher_fields={k:row.get(k) for k in ['jenis','noPeraturan','tahun_pengundangan','penerbit','status','last_updated','display','operasi']}))
        expected = len(rows)
    else:
        soup = BeautifulSoup(data, 'html.parser')
        text = normalized(soup.get_text(' ', strip=True)).lower()
        if any(x in text[:3500] for x in ['request rejected','access denied','maintenance','sedang dalam perbaikan','sedang dalam proses perbaikan','verify you are human']):
            raise ValueError('blocked_or_maintenance')
        if adapter in ('jateng_table','sulbar_table') and soup.select('.pagination a[href], .pager a[href], a[rel="next"]'):
            raise ValueError('unhandled_pagination_review_required')
        if adapter == 'jateng_table':
            counts = soup.select('.category-count')
            expected = sum(int(normalized(c.get_text())) for c in counts) if counts else None
            for row in soup.select('tr.info-row'):
                node = row.select_one('.info-cell-title')
                anchor = row.select_one('.info-cell-file a[href]')
                if not node or not anchor:
                    raise ValueError('catalogue_row_shape_changed')
                attachment = urljoin(url, anchor['href'])
                records.append(item(hashlib.sha256(attachment.encode()).hexdigest(), normalized(node.get_text(' ',strip=True)), url,
                                    download=attachment, attachment_url=attachment,
                                    external_attachment=not official_url(attachment)))
        elif adapter == 'sulbar_table':
            for a in soup.select('a[href*="katalog.php?id="]'):
                row = a.find_parent('tr'); cells = row.find_all('td',recursive=False)
                if len(cells) < 3:
                    raise ValueError('catalogue_row_shape_changed')
                label, numyear, title = [normalized(x.get_text(' ',strip=True)) for x in cells[:3]]
                match = re.fullmatch(r'(.+?)\s*/\s*((?:19|20)\d{2})',numyear)
                if not match:
                    raise ValueError('catalogue_number_shape_changed')
                heading = label+' Nomor '+match.group(1)+' Tahun '+match.group(2)+' tentang '+title
                detail = urljoin(url,a['href']); key=parse_qs(urlparse(detail).query)['id'][0]
                dl=row.select_one('a[href*="download.php"]')
                records.append(item(key,heading,url,detail,urljoin(url,dl['href']) if dl else None))
        elif adapter == 'kemendag_pages':
            count = re.search(r'menampilkan\s+\d+\s+dari\s+([\d,.]+)\s+peraturan', text)
            if not count:
                raise ValueError('catalogue_count_missing')
            expected = int(re.sub(r'\D', '', count.group(1)))
            for a in soup.select('h6 a[href]'):
                target = urljoin(url, a['href'])
                if urlparse(target).hostname != urlparse(url).hostname or not urlparse(target).path.startswith('/peraturan/'):
                    raise ValueError('catalogue_detail_left_scope')
                row = a.find_parent('div', class_='flex-grow-1')
                title = row.select_one('p') if row else None
                if not title:
                    raise ValueError('catalogue_row_shape_changed')
                heading = normalized(title.get_text(' ',strip=True))
                badges = [normalized(x.get_text(' ',strip=True)) for x in row.select('.badge-status')]
                # Truncated list titles are metadata, never a substitute for the final text.
                records.append(item(hashlib.sha256(target.encode()).hexdigest(),heading,url,target,
                    publisher_fields={'type':badges[0] if badges else None,
                      'status':next((b for b in badges if b in ('Berlaku','Tidak Berlaku')),None),
                      'record_slug':urlparse(target).path.rsplit('/',1)[-1],
                      'title_truncated':heading.endswith(('…','...'))}))
            for a in soup.select('.pagination a[href]'):
                target=urljoin(url,a['href']);parsed=urlparse(target)
                if parsed.hostname!=urlparse(url).hostname or parsed.path!='/peraturan' or not re.fullmatch(r'page=[1-9]\d*',parsed.query):
                    raise ValueError('unhandled_ministry_pagination')
                # The canonical entry already represents page one.
                if parsed.query!='page=1':links.append(target)
        elif adapter == 'djbc_pages':
            scope = re.fullmatch(r'(penerbit/\d+/[^/]+/)(\d+)\.html',parse_qs(urlparse(source['url']).query).get('page',[''])[0])
            if not scope:
                raise ValueError('invalid_djbc_scope')
            for a in soup.select('a[href]'):
                target=urljoin(url,a['href']); route=parse_qs(urlparse(target).query).get('page',[''])[0]
                if route.startswith('detail/'+scope.group(1).split('/',2)[0]+'/'+scope.group(1).split('/')[1]+'/'):
                    match=re.match(r'detail/penerbit/\d+/(\d+)/',route)
                    row=a.find_parent('tr');title=normalized(row.get_text(' ',strip=True) if row else a.get_text(' ',strip=True))
                    records.append(item(match.group(1),title,url,target))
                if re.fullmatch(re.escape(scope.group(1))+r'\d+\.html',route) and urlparse(target).netloc==urlparse(url).netloc:
                    links.append(target)
        else:
            raise ValueError('adapter_not_verified')
    if not records:
        raise ValueError('empty_listing_unverified')
    unique={}
    for r in records:
        key=r['source_record_id']
        if key in unique and unique[key] != r:
            raise ValueError('conflicting_record_id')
        unique[key]=r
    if expected is not None and adapter!='kemendag_pages' and expected != len(unique):
        raise ValueError('reported_count_mismatch')
    return list(unique.values()), sorted(set(links)), expected


def save(path, state):
    temp=path.with_suffix('.json.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(path)


def advance(snapshot, raw_dir, fetcher=fetch):
    url=snapshot['pending_urls'][0]
    data,actual,raw_hash=fetcher(url,raw_dir)
    records,links,expected=parse_page(data,actual,snapshot['source_config'])
    existing={r['source_record_id']:r for r in snapshot['records']}
    if snapshot['pages'] and not any(r['source_record_id'] not in existing for r in records):
        raise ValueError('pagination_no_progress')
    for r in records:
        prior=existing.get(r['source_record_id'])
        # List pagination may repeat a row, but two different identities must hold.
        if prior and {k:v for k,v in prior.items() if k!='page_url'} != {k:v for k,v in r.items() if k!='page_url'}:
            raise ValueError('conflicting_record_across_pages')
        existing.setdefault(r['source_record_id'],r)
    if len(existing)>5000:
        raise ValueError('catalogue_record_budget_exceeded')
    visited=set(snapshot['visited_urls']);visited.add(url)
    pending=[x for x in snapshot['pending_urls'][1:] if x not in visited]
    for target in links:
        if target not in visited and target not in pending:
            if not official_url(target) or urlparse(target).hostname != urlparse(snapshot['source_config']['url']).hostname:
                raise ValueError('pagination_left_registered_host')
            pending.append(target)
    if snapshot['source_config']['adapter']=='kemendag_pages':
        previous={p['reported_total'] for p in snapshot['pages']}
        if previous and previous!={expected}:
            raise ValueError('catalogue_total_changed_restart_review')
        if len(existing)>expected or not pending and len(existing)!=expected:
            raise ValueError('reported_count_mismatch')
    # Commit cursor and records together, after a fully validated page.
    snapshot['records']=list(existing.values());snapshot['visited_urls']=sorted(visited);snapshot['pending_urls']=pending
    snapshot['pages'].append(dict(url=url,actual_url=actual,raw_sha256=raw_hash,records=len(records),reported_total=expected,observed_at=now()))
    snapshot['status']='enumerated_scope' if not pending else 'partial'
    snapshot['stop_reason']='listing_exhausted' if not pending else 'more_pages'
    snapshot['finished_at']=now()


def run(registry, out, selected, max_pages=20, resume=False, fetcher=fetch, delay=3):
    out=Path(out).resolve();repo=Path(__file__).resolve().parents[2]
    if out==repo or repo in out.parents:
        raise ValueError('output_must_be_outside_repository')
    out.mkdir(parents=True,exist_ok=True,mode=0o700);out.chmod(0o700)
    path=out/'catalogue.json';raw=out/'raw';raw.mkdir(exist_ok=True,mode=0o700)
    with (out/'runner.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        config_hash=digest(registry)
        if path.exists():
            if not resume:raise ValueError('checkpoint_exists_use_resume_or_new_run')
            state=json.loads(path.read_text())
            if state['registry_sha256']!=config_hash:raise ValueError('registry_changed_start_new_run')
        else:
            if resume:raise ValueError('no_checkpoint_to_resume')
            state={'country':'IDN','registry_sha256':config_hash,'sources':[]}
            for source in registry:
                state['sources'].append(dict(run_id=str(uuid.uuid4()),source_id=source['source_id'],source_config=source,
                    started_at=now(),finished_at=now(),status='pending',stop_reason='not_started',pending_urls=[source['url']],
                    visited_urls=[],records=[],pages=[],failures=[]))
        used=0;blocked=set()
        for snapshot in state['sources']:
            if selected and snapshot['source_id'] not in selected:continue
            if snapshot['status'] in ('enumerated_scope','held','failed'):continue
            host=urlparse(snapshot['source_config']['url']).hostname
            if snapshot['source_config']['adapter']=='unverified':
                snapshot.update(status='held',stop_reason='adapter_not_verified',finished_at=now());save(path,state);continue
            while snapshot['pending_urls'] and used<max_pages:
                if (out/'STOP').exists():
                    snapshot.update(status='partial',stop_reason='operator_stop',finished_at=now());save(path,state);return state
                if host in blocked:
                    snapshot.update(status='held',stop_reason='host_blocked_earlier_in_run',finished_at=now());save(path,state);break
                used+=1
                try:advance(snapshot,raw,fetcher)
                except Exception as exc:
                    detail=str(exc)[:500];status=getattr(getattr(exc,'response',None),'status_code',None)
                    if status in (403,429) or 'blocked_or_maintenance' in detail:blocked.add(host)
                    snapshot['failures'].append(dict(url=snapshot['pending_urls'][0],error=detail,observed_at=now()))
                    snapshot.update(status='failed',stop_reason='page_failed_cursor_preserved',finished_at=now())
                save(path,state)
                print(json.dumps(dict(source=snapshot['source_id'],status=snapshot['status'],records=len(snapshot['records']),pending=len(snapshot['pending_urls']))),flush=True)
                if snapshot['status']=='failed':break
                if delay:time.sleep(delay)
            if used>=max_pages and snapshot['pending_urls'] and snapshot['status']!='failed':
                snapshot.update(status='partial',stop_reason='page_budget',finished_at=now());save(path,state)
        save(path,state);return state


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--registry',type=Path,default=Path(__file__).with_name('catalogue-sources.json'))
    p.add_argument('--output-dir',required=True);p.add_argument('--source',action='append');p.add_argument('--max-pages',type=int,default=20);p.add_argument('--resume',action='store_true');args=p.parse_args()
    registry=json.loads(args.registry.read_text())
    if not 1<=args.max_pages<=100 or len({x['source_id'] for x in registry})!=len(registry):p.error('invalid registry/page budget')
    if any(not official_url(x['url']) for x in registry) or args.source and not set(args.source)<={x['source_id'] for x in registry}:p.error('invalid official source')
    run(registry,args.output_dir,set(args.source or []),args.max_pages,args.resume)
