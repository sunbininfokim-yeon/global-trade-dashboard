#!/usr/bin/env python3
"""Connect one state's reviewed House roster to future poll discovery."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from election_watch.polls import read,atomic
from election_watch.federal_poll_ballots import link_house_ballots
from election_watch.superpac import STATES

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',choices=STATES,required=True)
    p.add_argument('--as-of',default=datetime.now(timezone.utc).date().isoformat())
    args=p.parse_args();path=ROOT/'config/usa_polls/ballot_reviews_2026.json'
    ballots,added=link_house_ballots(read(path),read(ROOT/'config/federal_matchups/2026.json'),args.state,args.as_of)
    if added:atomic(path,ballots)
    print({'state':args.state,'house_poll_rosters_added':len(added)})
    return 0


if __name__=='__main__':raise SystemExit(main())
