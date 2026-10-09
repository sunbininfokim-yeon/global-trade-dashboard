"""Publish a single state's reviewed poll capture without refreshing other states."""
from collections import Counter
from copy import deepcopy
from .polls import require
from .poll_house_focus import attach_house_focus


def merge_capture(previous, capture, state, receipt):
    require(previous['schema']==capture['schema']=='usa_live_polls_v1'
            and previous['cycle']==capture['cycle']==receipt['cycle'] and receipt['state']==state,
            'state polling capture schema/cycle')
    ids={rid for rid,r in previous['races'].items() if r['state']==state}
    require(ids and ids==set(capture['races']) and all(r['state']==state for r in capture['races'].values()),
            'state polling capture race universe')
    require(capture['source_status'] in ('ok','replay'),'unsuccessful state capture')
    result=deepcopy(previous)
    for rid,race in capture['races'].items():
        result['races'][rid]={**deepcopy(race),'fetched_at':capture['fetched_at'],
                              'as_of':capture['as_of'],'source_status':capture['source_status'],
                              'source_url':capture['source']['request_url']}
    result['review_queue']=[r for r in previous['review_queue'] if r['race_id'] not in ids]+deepcopy(capture['review_queue'])
    observations=[p for r in result['races'].values() for p in r['observations']]
    result['coverage'].update(accepted_observations=len(observations),displayed_observations=len(observations),
        excluded_observations=len(result['review_queue']),
        aggregation_eligible_observations=sum(p['aggregation_eligibility']['eligible'] for p in observations),
        reference_only_observations=sum(not p['aggregation_eligibility']['eligible'] for p in observations),
        exclusion_reasons=dict(Counter(r['reason'] for r in result['review_queue'])))
    coverage=result['monitoring']['race_coverage']
    coverage.update(deepcopy(capture['monitoring']['race_coverage']))
    for group,reason in [('requested_states','requested_state'),('cook_toss_up_and_lean','cook_toss_up_and_lean'),
                         ('korean_company_facilities','korean_company_facility')]:
        members=[r for r in coverage.values() if reason in r['priority']['reasons']]
        result['monitoring']['groups'][group]={'race_count':len(members),
            'with_observations':sum(r['accepted_count']>0 for r in members),
            'recent_7d':sum(r['windows']['7']['pollster_count']>0 for r in members),
            'recent_14d':sum(r['windows']['14']['pollster_count']>0 for r in members)}
    gaps=result['data_gaps']
    gaps['races'].update(deepcopy(capture['data_gaps']['races']))
    gaps['states'][state]=deepcopy(capture['data_gaps']['states'][state])
    for office,counts in gaps['counts_by_office'].items():
        rows=[r for r in gaps['races'].values() if r['office']==office]
        counts.update(with_polls=sum(r['poll_observation_count']>0 for r in rows),
            with_recent_7d=sum(r['recent_7d_pollsters']>0 for r in rows),
            with_recent_14d=sum(r['recent_14d_pollsters']>0 for r in rows))
    gaps['ballot_counts']=dict(Counter(r['ballot_competition']['status'] for r in gaps['races'].values()))
    for site in (result.get('company_interest') or {}).get('sites',[]):
        if site['state']!=state:continue
        for link in site.get('race_joins',[]):
            if link['race_id'] in ids:
                link['poll_coverage_status']=coverage[link['race_id']]['status']
                link['polls_monitored']=True
    result.setdefault('state_captures',{})[state]=deepcopy(receipt)
    if result.get('house_poll_focus'):
        attach_house_focus(result, {'house_poll_focus': result['house_poll_focus']})
    return result
