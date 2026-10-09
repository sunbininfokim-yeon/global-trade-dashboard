#!/usr/bin/env python3
"""Fetch public polls and refresh one state's reviewed race slots only."""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
from election_watch.polls import read,atomic,require
from election_watch.live_polls import fetch_polls,apply_watchlist,build_live,poll_history
from election_watch.poll_priorities import apply_priorities,attach_coverage,load_finance_links
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_gaps import attach_gaps
from election_watch.state_poll_capture import merge_capture
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.superpac import STATES

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',choices=STATES,required=True)
    parser.add_argument('--as-of',default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--public',type=Path,default=ROOT.parent.parent/'public/data')
    parser.add_argument('--packet', action='store_true', help='Save state-owned reviewed input; leave national outputs untouched')
    args=parser.parse_args();config=ROOT/'config/usa_polls'
    target=args.public/'usa_election_live_polls_v1.json'
    health=args.public/'usa_election_state_poll_status_v1.json'
    checked=datetime.now(timezone.utc).isoformat()
    status=read(health) if health.exists() else {'schema':'usa_state_poll_status_v1','states':{}}
    try:
        previous=read(target)
        policy=apply_priorities(apply_watchlist(read(config/'live_2026.json'),read(config/'watchlist_2026.json')),
            read(config/'priorities_2026.json'),args.public/'congressional_districts/USA',args.as_of)
        policy=apply_matchups(policy,read(ROOT/'config/governor_matchups/2026.json'),args.as_of)
        ballots=read(config/'ballot_reviews_2026.json')
        policy=apply_targets(policy,read(config/'targets_2026.json'),ballots,args.as_of)
        quality=read(config/'quality_reviews_2026.json')
        require(quality['schema']=='usa_poll_quality_reviews_v1' and quality['cycle']==policy['cycle'],
                'quality review schema/cycle')
        policy['quality_reviews']=quality['reviews']
        policy['races']={rid:r for rid,r in policy['races'].items() if r['state']==args.state}
        policy['states']=[args.state]
        rows,url=fetch_polls(policy['cycle'],args.as_of)
        provider_rows=rows
        rows,primary_receipts=merge_primary_supplements(rows,read(config/'primary_supplements_2026.json'),args.as_of,[args.state])
        capture=build_live(rows,policy,read(config/'results_2026.json'),args.as_of,checked,url)
        finance=load_finance_links(args.public/'usa_election_finance_index_v1.json',2026)
        attach_coverage(capture,provider_rows,policy,finance);attach_gaps(capture,finance)
        old_receipt=previous.get('state_captures',{}).get(args.state,{})
        receipt={**old_receipt,'state':args.state,'cycle':2026,'source_url':url,'captured_at':checked,
            'capture_kind':'provider_transport_and_reviewed_primary_supplements' if primary_receipts else 'provider_transport_only',
            'primary_supplement_receipts':primary_receipts,
            'serialized_provider_response_sha256':hashlib.sha256(json.dumps(provider_rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
            'provider_records':sum(r['provider_record_count'] for r in capture['monitoring']['race_coverage'].values())}
        if args.packet:
            from election_watch.state_inputs import digest
            path = ROOT/'config/state_evidence/2026'/f'{args.state}.json'
            packet = read(path) if path.exists() else {'schema':'usa_state_evidence_packet_v1',
                'state':args.state, 'cycle':2026, 'config_operations':[]}
            subjects = {(r['subject'], r['poll_type']) for r in policy['races'].values()}
            selected_rows = [r for r in provider_rows if (r.get('subject'), r.get('poll_type')) in subjects]
            packet['capture'] = {'as_of':args.as_of, 'fetched_at':checked, 'receipt':receipt,
                'provider_records':selected_rows, 'provider_records_sha256':digest(selected_rows),
                'primary_records':[r for r in rows if r.get('primary_source_capture')
                    and (r.get('subject'), r.get('poll_type')) in subjects]}
            atomic(path, packet)
            print({'state':args.state, 'saved':'state_input_packet', 'national_outputs_changed':False})
            return 0
        board=merge_capture(previous,capture,args.state,receipt)
        board['target_catalog']['ballot_review_count']=len(ballots['races'])
        archive=args.public/'usa_election_poll_history_2026.json'
        history=read(archive)
        new_history=poll_history(rows,policy,args.as_of)
        history['races']={rid:r for rid,r in history['races'].items() if rid not in capture['races']}
        history['races'].update({rid:{**r,'as_of':args.as_of,'fetched_at':checked} for rid,r in new_history['races'].items()})
        history['race_count']=len(history['races'])
        history['observation_count']=sum(len(r['observations']) for r in history['races'].values())
        atomic(archive,history);atomic(target,board)
        status['states'][args.state]={'status':'ok','checked_at':checked,'provider_records':receipt['provider_records'],
                                    'accepted_observations':capture['coverage']['displayed_observations']}
        atomic(health,status)
        print(status['states'][args.state])
    except (OSError,ValueError,TypeError,KeyError) as error:
        status['states'][args.state]={'status':'error_last_valid_preserved','checked_at':checked,'error_type':type(error).__name__}
        if not args.packet: atomic(health,status)
        print(status['states'][args.state]);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
