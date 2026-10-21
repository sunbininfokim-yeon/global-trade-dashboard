#!/usr/bin/env python3
"""Build an unpublished, repeatable review queue from discovery/Cursor inputs."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from election_watch.polls import read, atomic
from election_watch.poll_intake import discovery_candidates, research_candidates, build_intake, research_tasks

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--discovery',type=Path)
    p.add_argument('--research-dossier',type=Path,action='append',default=[])
    p.add_argument('--previous',type=Path)
    p.add_argument('--board',type=Path,default=ROOT.parent.parent/'public/data/usa_election_live_polls_v1.json')
    p.add_argument('--as-of',default=datetime.now(timezone.utc).date().isoformat())
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--tasks-output',type=Path,help='Write ordered research jobs for Cursor; never an approval file')
    args = p.parse_args()
    if not args.discovery and not args.research_dossier:
        p.error('supply --discovery or --research-dossier')
    catalog = read(ROOT/'config/usa_polls/targets_2026.json')
    board = read(args.board); candidates=[]; rejected=[]; health={}
    if args.discovery:
        report = read(args.discovery)
        candidates,rejected = discovery_candidates(report,catalog)
        health = report.get('source_health',{})
        for result in report.get('research_intake',[]):
            candidates.extend(result['candidates']); rejected.extend(result['rejected_inputs'])
    for path in args.research_dossier:
        rows,bad = research_candidates(read(path),path.parent,catalog,args.as_of)
        candidates.extend(rows); rejected.extend(bad)
    previous = read(args.previous) if args.previous else None
    result = build_intake(candidates,board,args.as_of,datetime.now(timezone.utc).isoformat(),previous,health,rejected)
    atomic(args.output,result)
    if args.tasks_output:
        atomic(args.tasks_output,research_tasks(result,board))
    print(result['summary'])
    return 0


if __name__=='__main__':
    raise SystemExit(main())
