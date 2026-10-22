"""One bounded availability check per original ministry host. No DB/AI writes.

Reachable pages are not enumerated catalogues. Held snapshots can be imported
with import-catalogue.cjs without replacing previously saved catalogue rows.
"""
import argparse
import fcntl
import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from catalogue import now, save
from collect import fetch, normalized, official_url


def probe_url(source):
    url=source.get('verification',{}).get('observed_listing_url') or source['url']
    if not official_url(url) or urlparse(url).hostname!=urlparse(source['url']).hostname:
        raise ValueError('probe_must_stay_on_registered_official_host')
    return url


def inspect_response(data,url,source):
    soup=BeautifulSoup(data,'html.parser')
    text=normalized(soup.get_text(' ',strip=True));low=text.lower()
    if any(x in low[:3500] for x in ['maintenance','sedang dalam perbaikan','sedang dalam proses perbaikan']):
        outcome='maintenance'
    elif any(x in low[:3500] for x in ['request rejected','access denied','verify you are human']):
        outcome='blocked_page'
    elif 'loading peraturan' in low or 'loading chart' in low:
        outcome='reachable_dynamic_shell_unverified'
    else:
        outcome='reachable_catalogue_unverified'
    links=[]
    for a in soup.select('a[href]'):
        target=urljoin(url,a['href'])
        if official_url(target) and urlparse(target).hostname==urlparse(source['url']).hostname and target not in links:
            links.append(target)
    return dict(outcome=outcome,title=normalized(soup.title.get_text())[:250] if soup.title else None,
                observed_links=links[:100],enumeration_verified=False)


def check(source,raw_dir,fetcher=fetch):
    url=probe_url(source);result=dict(url=url,checked_at=now())
    try:
        data,actual,h=fetcher(url,raw_dir)
        if not official_url(actual) or urlparse(actual).hostname!=urlparse(source['url']).hostname:
            raise ValueError('probe_redirect_left_registered_host')
        if hashlib.sha256(data).hexdigest()!=h:raise ValueError('probe_response_hash_mismatch')
        result.update(actual_url=actual,raw_sha256=h,**inspect_response(data,actual,source))
    except Exception as exc:
        if isinstance(exc,OSError) and exc.errno==28:raise
        status=getattr(getattr(exc,'response',None),'status_code',None);name=type(exc).__name__
        # Never copy headers, cookies, opaque memory addresses or environment values.
        outcome='http_'+str(status) if status else 'connection_timeout' if name=='ConnectTimeout' else 'read_timeout' if name=='ReadTimeout' else 'probe_error'
        result.update(outcome=outcome,http_status=status,error_type=name,enumeration_verified=False)
    result['finished_at']=now();return result


def snapshot(source,observation):
    if observation['url']!=probe_url(source) or observation.get('enumeration_verified') is not False:
        raise ValueError('invalid_probe_observation')
    return dict(run_id=str(uuid.uuid4()),source_id=source['source_id'],source_config={**source,'verification':{**source.get('verification',{}),**observation}},
                started_at=observation['checked_at'],finished_at=observation['finished_at'],
                status='held',stop_reason=observation['outcome'],records=[],pages=[],
                pending_urls=[observation['url']],visited_urls=[],
                failures=[{k:observation[k] for k in ['url','checked_at','outcome','http_status','raw_sha256','error_type'] if k in observation}])


def run(registry,out,selected,fetcher=fetch,delay=3):
    out=Path(out).resolve();repo=Path(__file__).resolve().parents[2]
    if out==repo or repo in out.parents:raise ValueError('output_must_be_outside_repository')
    sources=[s for s in registry if s['source_id'] in selected]
    if not sources or {s['source_id'] for s in sources}!=set(selected) or len(sources)>10:
        raise ValueError('invalid_probe_scope')
    if any(s['adapter']!='unverified' or not s['source_id'].endswith('-original') for s in sources):
        raise ValueError('probe_only_unverified_original_ministries')
    if len({urlparse(probe_url(s)).hostname for s in sources})!=len(sources):raise ValueError('one_probe_per_host')
    out.mkdir(parents=True,exist_ok=True,mode=0o700);out.chmod(0o700)
    raw=out/'raw';raw.mkdir(exist_ok=True,mode=0o700)
    state=dict(country='IDN',purpose='Availability checks; no enumerated laws',sources=[])
    with (out/'runner.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'catalogue.json').exists():raise ValueError('use_new_probe_output')
        for s in sources:
            if (out/'STOP').exists():break
            if shutil.disk_usage(out).free<64*1024*1024:raise OSError('insufficient_local_disk_space')
            observation=check(s,raw,fetcher);state['sources'].append(snapshot(s,observation));save(out/'catalogue.json',state)
            print(json.dumps(dict(source=s['source_id'],outcome=observation['outcome'],enumeration_verified=False)),flush=True)
            if delay:time.sleep(delay)
        save(out/'catalogue.json',state)
    return state


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--registry',type=Path,default=Path(__file__).with_name('catalogue-sources.json'))
    p.add_argument('--source',action='append',required=True);p.add_argument('--output-dir',required=True)
    a=p.parse_args();run(json.loads(a.registry.read_text()),a.output_dir,set(a.source))
