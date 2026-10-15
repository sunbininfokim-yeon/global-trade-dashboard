"""Current configuration clock, separate from fixed historical poll scenarios."""
import json
from pathlib import Path
from election_watch.polls import read

ROOT=Path(__file__).resolve().parents[1]
def review_dates(value):
    if isinstance(value,dict):
        for k,v in value.items():
            if k in ('reviewed_on','ballot_reviewed_on') and isinstance(v,str):yield v
            else:yield from review_dates(v)
    elif isinstance(value,list):
        for v in value:yield from review_dates(v)
SNAPSHOT_DAY=max(d for path in ('config/federal_matchups/2026.json',
    'config/governor_matchups/2026.json','config/governor_matchups/2026_ballot_reviews.json',
    'config/usa_polls/ballot_reviews_2026.json')
    for d in review_dates(read(ROOT/path)))

def published_snapshot_day(board, catalog_day):
    """A state capture may be newer than the unchanged national anchor date."""
    return max(catalog_day, board['as_of'], *(r.get('as_of', board['as_of'])
               for r in board['races'].values()))


# Published joins use current catalog AND per-race observation clocks. This
# never advances the board, receipt or historical normalization scenario dates.
PUBLIC_SNAPSHOT_DAY=published_snapshot_day(json.loads(
    (ROOT.parent.parent/'public/data/usa_election_live_polls_v1.json').read_text()), SNAPSHOT_DAY)
