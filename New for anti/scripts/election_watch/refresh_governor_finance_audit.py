#!/usr/bin/env python3
"""Read public governor disclosures whose totals still require normalization review."""
import argparse
from pathlib import Path
from election_watch.polls import read, atomic
from election_watch.governor_tn import collect_audit as collect_tn
from election_watch.governor_fl import collect_audit as collect_fl
from election_watch.governor_matchups import validate_snapshot
from election_watch.superpac import now, SourceError

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',choices=['TN','FL'],required=True)
    parser.add_argument('--cycle',type=int,default=2026)
    parser.add_argument('--public',type=Path,default=ROOT.parent.parent/'public/data')
    args=parser.parse_args()
    try:
        snapshot=read(ROOT/'config/governor_matchups'/f'{args.cycle}.json')
        validate_snapshot(snapshot,args.cycle,now()[:10])
        collector={'TN':collect_tn,'FL':collect_fl}[args.state]
        payload=collector(args.cycle,snapshot['contests'][args.state]['candidates'])
        atomic(args.public/'usa_governor_finance_audits'/str(args.cycle)/f'{args.state}.json',payload)
        print({'state':args.state,'status':payload['status'],'input_records':payload['input_records'],
               'current_governor_target_records':payload['current_governor_target_records']})
    except (OSError,ValueError,KeyError,TypeError,SourceError) as error:
        print({'status':'error_last_audit_preserved','error_type':type(error).__name__})
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
