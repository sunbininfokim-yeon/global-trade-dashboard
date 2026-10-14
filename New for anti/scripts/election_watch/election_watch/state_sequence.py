"""Ordered collection checkpoints. Transport success never means full coverage."""
from copy import deepcopy
from .polls import atomic,require
from .state_evidence import ordered_states


def state_range(plan,as_of,start,end):
    order=ordered_states(plan,as_of);states=[s for _,s in order]
    require(start in states and end in states and states.index(start)<=states.index(end),'invalid state sequence range')
    return order[states.index(start):states.index(end)+1]


def run_sequence(public,plan,selected,as_of,run_id,processor,previous=None):
    """Checkpoint each state and resume the same run without recollecting successes."""
    ids=[s for _,s in selected]
    order=ordered_states(plan,as_of)
    require(selected and selected==state_range(plan,as_of,ids[0],ids[-1]) and len(set(ids))==len(ids),
            'sequence does not follow plan')
    result={'schema':'usa_state_evidence_sequence_v1','cycle':2026,'run_id':run_id,
            'as_of':as_of,'selected_order':ids,'states':{},'deployment_hold':True,
            'note_ko':'실제 API 순차 수집 기록입니다. 공식 공시 완결·모든 조사 발견·원문 전수 검토와 구분합니다.'}
    if previous:
        require(all(previous[k]==result[k] for k in ('schema','cycle','run_id','as_of','selected_order')),
                'sequence resume scope mismatch')
        result=deepcopy(previous)
    for group,state in selected:
        if result['states'].get(state,{}).get('status')=='poll_transport_updated_partial':continue
        try:
            row=processor(state,group)
            require(row['state']==state and row['group']==group and row['status']=='poll_transport_updated_partial',
                    'sequence state result mismatch')
            result['states'][state]=row
        except (OSError,ValueError,KeyError,TypeError) as exc:
            result['states'][state]={'state':state,'group':group,'status':'failed_last_valid_preserved',
                                     'error_type':type(exc).__name__}
            result['blocked_state']=state
            result['status']='interrupted'
            atomic(public/'usa_election_state_sequence_v1.json',result)
            return result
        result['last_processed_state']=state
        result['next_state']=next((s for s in ids if s not in result['states'] or
                                  result['states'][s]['status']!='poll_transport_updated_partial'),None)
        result['status']='running'
        atomic(public/'usa_election_state_sequence_v1.json',result)
    result.pop('blocked_state',None)
    result.update(status='transport_sequence_completed_partial',next_state=None)
    atomic(public/'usa_election_state_sequence_v1.json',result)
    return result
