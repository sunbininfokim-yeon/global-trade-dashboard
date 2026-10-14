"""Freeze bounded work across month boundaries; an empty release is not zero."""
from copy import deepcopy
from datetime import datetime, timezone
from bilateral import ContractError
from bilateral_jobs import make_job

SETTLED = frozenset({'ok', 'empty'})
DEFER_AFTER_THREE = frozenset({'error', 'contract_error', 'provider_error', 'partial', 'world_only'})


def pending_ids(jobs, state, cycle):
    return [j['id'] for j in jobs if not (
        state.get('jobs', {}).get(j['id'], {}).get('cycle') == cycle
        and (state['jobs'][j['id']].get('status') in SETTLED or (
            state['jobs'][j['id']].get('status') in DEFER_AFTER_THREE
            and state['jobs'][j['id']].get('attempts', 0) >= 3)))]


def resume_plan(state, key, candidates, cycle):
    """Never replace an unfinished old plan with a new month's candidates.

    Empty responses settle only this cycle and retry next monthly cycle. Errors
    remain pending; execute_plan rotates by attempts. No observations are added.
    A same-cycle discovery may append new identities without requerying successes.
    """
    if not key or not cycle:
        raise ContractError('queue key and cycle required')
    plans = state.setdefault('active_plans', {})
    old = plans.get(key)
    if old:
        old['last_resume_at'] = datetime.now(timezone.utc).isoformat()
        for job in old['jobs']:
            if make_job(job['meta'], job['partners'])['id'] != job['id']:
                raise ContractError('stored plan identity mismatch')
        if pending_ids(old['jobs'], state, old['cycle']):
            return deepcopy(old)
        if old['cycle'] == cycle:
            candidates = list({j['id']: j for j in old['jobs'] + candidates}.values())
    for job in candidates:
        if make_job(job['meta'], job['partners'])['id'] != job['id']:
            raise ContractError('candidate identity mismatch')
    now = datetime.now(timezone.utc).isoformat()
    plan = {'cycle': cycle, 'jobs': deepcopy(candidates), 'created_at':now, 'last_resume_at':now}
    plans[key] = plan
    return deepcopy(plan)


def queue_health(state):
    result = {}
    for key, plan in state.get('active_plans', {}).items():
        cycle, jobs = plan['cycle'], plan['jobs']
        entries = [state.get('jobs', {}).get(j['id'], {}) for j in jobs]
        result[key] = dict(cycle=cycle, created_at=plan.get('created_at'),
            last_resume_at=plan.get('last_resume_at'), planned_jobs=len(jobs),
            pending_jobs=len(pending_ids(jobs,state,cycle)),
            empty_jobs=sum(e.get('cycle')==cycle and e.get('status')=='empty' for e in entries),
            deferred_error_jobs=sum(e.get('cycle')==cycle and e.get('status') in DEFER_AFTER_THREE
                                    and e.get('attempts',0)>=3 for e in entries))
    return result
