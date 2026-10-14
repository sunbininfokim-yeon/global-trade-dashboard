"""Connect missing House poll slots to already reviewed display rosters."""
from copy import deepcopy
from datetime import date
from .federal_matchups import validate_snapshot
from .polls import require
from .superpac import STATES


def link_house_ballots(ballots, federal, state, as_of):
    validate_snapshot(federal, as_of)
    require(state in STATES and ballots['schema']=='usa_poll_ballot_reviews_v1'
            and ballots['cycle']==federal['cycle']
            and date.fromisoformat(ballots['reviewed_on'])<=date.fromisoformat(as_of),
            'federal poll ballot scope/date')
    result=deepcopy(ballots); added=[]
    for rid,row in federal['races'].items():
        if row['state']!=state or row['office']!='house' or rid in result['races']:
            continue
        role=row.get('source_role')
        if role is None and row['status']=='certified_ballot':
            role='state_election_agency'
        require(role in ('state_election_agency','reviewed_secondary_nominee_listing'),
                'unreviewed House roster source role')
        # Retain the complete reviewed row, including agency exclusions and
        # election-system provenance. A thin copy would lose DISQ history when
        # the display publisher later reuses this polling review.
        review=deepcopy(row)
        # Do not import registrations, unconfirmed candidates or inferred aliases.
        # A one-candidate secondary listing does not establish an unopposed ballot.
        review['source_role']=role
        result['races'][rid]=review;added.append(rid)
    return result,added
