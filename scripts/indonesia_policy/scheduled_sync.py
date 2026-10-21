"""One resumable IDN refresh + catalogue discovery + strict automatic admission.

No paid AI and no mail sends. macOS launchd owns cadence; this process exits.
Only reviewed catalogue adapters run. Unknown adapters remain explicitly held.
"""
import argparse
import fcntl
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from automatic_admission import Held, prepare, validate_document
from catalogue import parse_page
from collect import collect, fetch, official_url, ORDER
from sync_reviewed import Gateway, DatabaseLease, atomic_json, load_manifest, run as refresh

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
ADAPTERS={'jateng_table','sulbar_table','djbc_pages','kemendag_pages','ildis_json'}

class Stopped(RuntimeError):
    pass

def stamp():
    return datetime.now(timezone.utc).isoformat()

def cooldown(error):
    code=getattr(getattr(error,'response',None),'status_code',None)
    return 86400 if code in (403,429) or any(w in str(error).lower() for w in ('blocked','maintenance')) else 3600

def catalogue_snapshot(source,raw,blocked,fetcher=fetch):
    now=stamp(); snapshot=dict(run_id=str(uuid.uuid4()),source_id=source['source_id'],source_config=source,
      started_at=now,finished_at=now,status='failed',stop_reason='first_page_unavailable',
      records=[],pages=[],failures=[],pending_urls=[source['url']])
    host=urlparse(source['url']).hostname
    if blocked.get(host,0)>time.time():
        snapshot.update(status='held',stop_reason='host_cooldown');return snapshot
    try:
        data,url,digest=fetcher(source['url'],raw)
        records,links,total=parse_page(data,url,source)
        snapshot.update(records=records,pages=[dict(url=source['url'],actual_url=url,raw_sha256=digest,reported_total=total,records=len(records),observed_at=now)],
          pending_urls=links,status='partial' if links or total is not None and total!=len(records) else 'enumerated_scope',
          stop_reason='head_window_only' if links or total is not None and total!=len(records) else 'listing_exhausted')
    except Exception as e:
        blocked[host]=time.time()+cooldown(e)
        snapshot['failures']=[dict(url=source['url'],error=str(e)[:300],observed_at=now)]
    snapshot['finished_at']=stamp()
    return snapshot

def admission_artifact(row,source,raw,blocked,collector=collect):
    result=dict(p_source_id=row['source_id'],p_source_record_id=row['source_record_id'],p_metadata_hash=row['metadata_hash'],
      p_document=None,p_outcome='held',p_reason='unclassified',p_retry_seconds=None)
    try:
        entry=prepare(row,source)
        host=urlparse(entry['url']).hostname
        if blocked.get(host,0)>time.time():
            result.update(p_reason='host_cooldown',p_retry_seconds=86400);return result
        doc=collector(entry,raw,{h for h,until in blocked.items() if until>time.time()})
        body_host=doc.get('body_fetch_blocked_host')
        if body_host:blocked[body_host]=time.time()+86400
        validate_document(doc,entry,row)
        result.update(p_document=doc,p_outcome='stored',p_reason='complete_official_heading_identity_verified; legal effect unverified',p_retry_seconds=86400)
    except Held as e:
        result.update(p_reason=str(e)[:300],p_retry_seconds=604800 if str(e)=='complete_official_text_unavailable' else None)
    except Exception as e:
        # Transient transport failures are retried after a bounded host pause.
        url=row['metadata'].get('detail_url') or row['metadata'].get('download_url')
        delay=cooldown(e)
        if url:blocked[urlparse(url).hostname]=time.time()+delay
        result.update(p_outcome='failed',p_reason=str(e)[:300],p_retry_seconds=delay)
    return result

def run(root,rpc,*,refresh_limit=20,discovery_limit=5,fetcher=fetch,collector=collect,pause=time.sleep,initial_cooldowns=None):
    root=Path(root).resolve()
    if root==REPO or REPO in root.parents:raise ValueError('scheduler state must be outside repository')
    if not 1<=refresh_limit<=20 or not 1<=discovery_limit<=20:raise ValueError('invalid collection budget')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (root/'STOP').exists():return dict(country='IDN',state='stopped',source_requests=0)
    with (root/'scheduler.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('IDN scheduled collector already running') from None
        sources=json.loads((HERE/'catalogue-sources.json').read_text())
        verified=[s for s in sources if s['adapter'] in ADAPTERS]
        if any(not official_url(s['url']) for s in verified) or len({s['source_id'] for s in sources})!=len(sources):raise ValueError('invalid official source registry')
        registry={s['source_id']:s for s in verified}
        state_path=root/'active-run.json'
        state=json.loads(state_path.read_text()) if state_path.exists() else None
        if not state or state.get('complete'):
            state=dict(version=1,run_id=str(uuid.uuid4()),started_at=stamp(),phase='refresh',source_index=0,candidate_index=0,
              complete=False,cooldowns=(state or {}).get('cooldowns',dict(initial_cooldowns or {})),sources=list(registry),
              result=dict(country='IDN',catalogues=0,catalogue_failures=0,admitted=0,new_versions=0,held=0,failed=0,
                unsupported_sources=[s['source_id'] for s in sources if s['adapter'] not in ADAPTERS]))
            atomic_json(state_path,state)
        if state.get('version')!=1 or state.get('sources')!=list(registry):raise ValueError('scheduler registry changed; preserve old checkpoint before restarting')
        if str(uuid.UUID(state['run_id']))!=state['run_id'] or state['phase'] not in ('refresh','catalogues','admission') or type(state['source_index']) is not int or not 0<=state['source_index']<=len(verified):raise ValueError('invalid scheduler checkpoint')
        work=root/'runs'/state['run_id'];work.mkdir(parents=True,exist_ok=True,mode=0o700)
        raw=root/'raw';raw.mkdir(exist_ok=True,mode=0o700)
        # Retain official originals; stop rather than grow without a bound.
        if sum(p.stat().st_size for p in root.rglob('*') if p.is_file())>1024**3:raise RuntimeError('IDN state/cache exceeds 1 GiB; review retained originals before resuming')
        def checkpoint():atomic_json(state_path,state)
        def boundary(lease):
            if (root/'STOP').exists():raise Stopped('operator stop')
            lease.heartbeat()
        with DatabaseLease(rpc,'mac-scheduled:'+str(os.getpid())) as lease:
            try:
                if state['phase']=='refresh':
                    boundary(lease)
                    manifest=sorted(load_manifest(),key=lambda e:(ORDER.index(e['primary_stage']),e['document_id']))
                    state['result']['refresh']=refresh(manifest,root/'reviewed',lease,limit=refresh_limit,collect_fn=collector,
                      heartbeat=lambda:boundary(lease),pause=pause,external_cooldowns=state['cooldowns'])
                    state['cooldowns'].update(json.loads((root/'reviewed'/'status.json').read_text())['cooldowns'])
                    state['phase']='catalogues';checkpoint()
                if state['phase']=='catalogues':
                    for index in range(state['source_index'],len(verified)):
                        boundary(lease);source=verified[index];artifact=work/('catalogue-'+source['source_id']+'.json')
                        if artifact.exists():saved=json.loads(artifact.read_text());snapshot=saved['snapshot'];state['cooldowns'].update(saved['cooldowns'])
                        else:
                            snapshot=catalogue_snapshot(source,raw,state['cooldowns'],fetcher)
                            atomic_json(artifact,dict(snapshot=snapshot,cooldowns=state['cooldowns']))
                        response=lease('idn_store_catalogue',{'p_snapshot':snapshot})
                        if not isinstance(response,dict) or type(response.get('changed')) is not bool:raise RuntimeError('IDN catalogue acknowledgment missing')
                        state['result']['catalogues']+=1;state['result']['catalogue_failures']+=int(snapshot['status'] in ('held','failed'))
                        state['source_index']=index+1;checkpoint()
                        print(json.dumps(dict(phase='catalogue',source=source['source_id'],state=snapshot['status'],records=len(snapshot['records']))),flush=True)
                        pause(3)
                    state['phase']='admission';checkpoint()
                if state['phase']=='admission':
                    queue_path=work/'queue.json'
                    if queue_path.exists():queue=json.loads(queue_path.read_text())
                    else:
                        queue=rpc('idn_ingestion_queue',{'p_source_ids':list(registry),'p_limit':discovery_limit})
                        if queue.get('country')!='IDN' or not isinstance(queue.get('items'),list):raise RuntimeError('invalid IDN ingestion queue')
                        atomic_json(queue_path,queue)
                    if type(state['candidate_index']) is not int or not 0<=state['candidate_index']<=len(queue['items']) or len(queue['items'])>20:raise ValueError('invalid admission cursor')
                    for index in range(state['candidate_index'],len(queue['items'])):
                        boundary(lease);row=queue['items'][index];artifact=work/('candidate-'+str(index)+'.json')
                        if artifact.exists():saved=json.loads(artifact.read_text());item=saved['item'];state['cooldowns'].update(saved['cooldowns'])
                        else:
                            item=admission_artifact(row,registry[row['source_id']],raw,state['cooldowns'],collector)
                            atomic_json(artifact,dict(item=item,cooldowns=state['cooldowns']))
                        if any(item['p_'+k]!=row[k] for k in ('source_id','source_record_id','metadata_hash')):raise ValueError('admission artifact identity mismatch')
                        if item.get('p_document') is not None:validate_document(item['p_document'],prepare(row,registry[row['source_id']]),row)
                        response=lease.complete_ingestion(item)
                        if not isinstance(response,dict) or type(response.get('new_version')) is not bool:raise RuntimeError('IDN ingestion acknowledgment missing')
                        if not response.get('stale'):
                            state['result']['new_versions']+=int(response['new_version'])
                            field={'stored':'admitted','held':'held','failed':'failed'}[item['p_outcome']]
                            state['result'][field]+=1
                        state['candidate_index']=index+1;checkpoint()
                        print(json.dumps(dict(phase='admission',source=row['source_id'],record=row['source_record_id'],state=item['p_outcome'],new_version=response['new_version'],reason=item['p_reason'])),flush=True)
                        pause(3)
                state.update(complete=True,finished_at=stamp());state['result']['state']='partial' if state['result']['catalogue_failures'] or state['result']['failed'] or state['result']['refresh']['state']!='ok' else 'ok'
                checkpoint();atomic_json(root/'last-run.json',{**state['result'],'run_id':state['run_id'],'started_at':state['started_at'],'finished_at':state['finished_at']})
                return state['result']
            except Stopped:
                checkpoint();return dict(country='IDN',state='stopped',checkpoint=state['phase'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state-dir',required=True);p.add_argument('--env-file');p.add_argument('--write',action='store_true')
    p.add_argument('--refresh-limit',type=int,default=20);p.add_argument('--discovery-limit',type=int,default=5)
    p.add_argument('--initial-cooldown-file',type=Path,help='Import prior host cooldowns only when creating initial state');args=p.parse_args()
    if not args.write:print(json.dumps(dict(country='IDN',mode='preview',network=False,database_writes=False)));return
    blocked=json.loads(args.initial_cooldown_file.read_text()).get('cooldowns',{}) if args.initial_cooldown_file and args.initial_cooldown_file.exists() else None
    print(json.dumps(run(args.state_dir,Gateway(args.env_file),refresh_limit=args.refresh_limit,discovery_limit=args.discovery_limit,initial_cooldowns=blocked)),flush=True)

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError) as e:raise SystemExit(str(e))
