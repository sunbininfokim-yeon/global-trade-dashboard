"""Current configuration clock, separate from fixed historical poll scenarios."""
import json
from pathlib import Path

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
    for d in review_dates(json.loads((ROOT/path).read_text())))
