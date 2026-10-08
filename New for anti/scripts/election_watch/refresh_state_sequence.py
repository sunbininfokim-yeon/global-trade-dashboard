#!/usr/bin/env python3
"""Collect states serially in the reviewed A-E order; no merge or deployment."""
import argparse,fcntl,hashlib,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
from election_watch.polls import read,require
from election_watch.state_sequence import state_range,run_sequence

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--from-state',required=True);p.add_argument('--through-state',default='WY')
    p.add_argument('--as-of',default=datetime.now(timezone.utc).date().isoformat())
    p.add_argument('--run-id',required=True)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--public',type=Path,default=ROOT.parent.parent/'public/data')
    args=p.parse_args();plan=read(ROOT/'config/usa_polls/state_evidence_plan_2026.json')
    selected=state_range(plan,args.as_of,args.from_state,args.through_state)
    previous=read(args.public/'usa_election_state_sequence_v1.json') if args.resume else None
    lock_key=hashlib.sha256(str(args.public.resolve()).encode()).hexdigest()[:16]
    lock=Path(tempfile.gettempdir())/f'usa-state-sequence-{lock_key}.lock'
    with lock.open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print({'status':'another_sequence_running'});return 1
        def process(state,group):
            checked=datetime.now(timezone.utc).isoformat()
            for script,extra in [('refresh_poll_ballot_links.py',[]),('refresh_state_polls.py',['--public',str(args.public)]),
                                 ('refresh_state_evidence.py',['--public',str(args.public),'--polls',str(args.public/'usa_election_live_polls_v1.json')])]:
                completed=subprocess.run([sys.executable,str(ROOT/script),'--state',state,'--as-of',args.as_of,*extra],
                                         capture_output=True,text=True)
                require(completed.returncode==0,f'{script} failed')
            health=read(args.public/'usa_election_state_poll_status_v1.json')['states'][state]
            index=read(args.public/'usa_election_state_evidence_index_v1.json')
            item=index['states'][state];asset=read(args.public/item['data_file'])
            row={'state':state,'group':group,'status':'poll_transport_updated_partial','checked_at':checked,
                'poll_capture':health,'office_coverage':asset['office_coverage'],
                'governor_source_status':item['governor_source_status'],'source_dates':item['source_dates'],
                'finance_collection':'not_run_existing_observations_preserved',
                'primary_source_review':asset['work_status']}
            print({'state':state,'provider_records':health['provider_records'],
                   'accepted_observations':health['accepted_observations'],'governor':item['governor_source_status']},flush=True)
            return row
        result=run_sequence(args.public,plan,selected,args.as_of,args.run_id,process,previous)
        print({'status':result['status'],'processed_states':len(result['states']),
               'next_state':result.get('next_state'),'blocked_state':result.get('blocked_state')})
        return int(result['status']!='transport_sequence_completed_partial')


if __name__=='__main__':raise SystemExit(main())
