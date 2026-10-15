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

# Tests that deliberately join the published board must use that board's clock.
# Historical normalization tests keep their fixed scenario dates separately.
_public_board=json.loads((ROOT.parent.parent/'public/data/usa_election_live_polls_v1.json').read_text())
# State packet projections preserve the national collection date. A newer
# state's observed date is not a future observation relative to this fixture.
PUBLIC_SNAPSHOT_DAY=max(SNAPSHOT_DAY, _public_board['as_of'],
    *(race.get('as_of', _public_board['as_of']) for race in _public_board['races'].values()))
