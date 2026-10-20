"""Persistent document review queue, separate from admitted polling observations.

Discovery links and Cursor dossiers share this path. Neither a claimed approval
nor a local document hash can grant national polling admission.
"""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import math
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .polls import digest, require
from .poll_source_discovery import safe_link

SCHEMA = 'usa_poll_intake_v1'
PRIORITY_STATES = ['NY','TN','GA','FL','PA','MI','WI','AZ','NV','NC','TX']


def canonical_url(value):
    parsed = urlsplit(safe_link(value))
    require(parsed.scheme=='https' and parsed.port in (None,443), 'intake URL scheme/port')
    query = [(k,v) for k,v in parse_qsl(parsed.query,keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')]
    return urlunsplit(('https',parsed.netloc.lower(),parsed.path,urlencode(query),parsed.fragment))


def scheduled_race(state, office, district, catalog):
    require(state in catalog['states'], 'unknown research state')
    if office == 'house':
        seats = catalog['states'][state]['house_seats']
        require(isinstance(district,str) and re.fullmatch(r'\d{1,2}|AL',district), 'missing research district')
        number = 1 if district in ('00','AL') and seats == 1 else int(district) if district.isdigit() else 0
        require(1 <= number <= seats, 'research district outside current map')
        return f'USA:{state}:house:'+('00' if seats == 1 else f'{number:02}')
    require(office in ('senate','governor') and district is None
            and state in catalog[office+'_states'], 'unscheduled research office')
    return f'USA:{state}:{office}'


def discovery_candidates(report, catalog):
    require(report.get('schema') == 'usa_poll_source_discovery_v1'
            and report.get('cycle') == catalog['cycle'], 'intake discovery schema/cycle')
    stamp = report['captured_at']; datetime.fromisoformat(stamp.replace('Z','+00:00'))
    rows = []; rejected = []
    for entry in report.get('records',[]):
        if not isinstance(entry,dict):
            rejected.append({'input_id':None,'error_type':'InvalidRecord'}); continue
        try:
            url = canonical_url(entry['source_url']); rid = entry.get('race_id')
            if rid:
                parts = rid.split(':')
                require(len(parts) in (3,4) and parts[0]=='USA', 'invalid discovered race ID')
                normalized = scheduled_race(parts[1],parts[2],parts[3] if len(parts)==4 else None,catalog)
                require(rid == normalized, 'discovered race normalization conflict')
            evidence = {k:deepcopy(v) for k,v in entry.items()
                        if k not in ('captured_at','id','signal_eligible','status','provider_source_url_matches')}
            rows.append({'race_id':rid, 'source_url':url, 'seen_at':stamp,
                'kind':'publisher_or_aggregator_discovery', 'evidence':evidence,
                'reasons':['primary_document_review_required']+([] if rid else ['race_identity_unresolved'])})
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            rejected.append({'input_id':entry.get('id'),'error_type':type(exc).__name__})
    return rows, rejected


def research_candidates(dossier, directory, catalog, as_of, captured_at=None):
    """Validate file integrity and required fields; transcriptions remain unapproved."""
    require(dossier.get('schema')=='usa_state_research_dossier_v1'
            and dossier.get('cycle')==catalog['cycle'], 'research dossier schema/cycle')
    state = dossier['state']; require(state in catalog['states'], 'research dossier state')
    require(date.fromisoformat(dossier['checked_on'])<=date.fromisoformat(as_of), 'future research dossier')
    seen_at = captured_at or datetime.now(timezone.utc).isoformat()
    root = Path(directory).resolve(); rows = []; rejected = []
    for poll in dossier.get('polls',[]):
        if not isinstance(poll,dict):
            rejected.append({'input_id':None,'error_type':'InvalidRecord'}); continue
        try:
            url = canonical_url(poll['source_url'])
            local = Path(poll['local_file'])
            path = (root/local).resolve()
            require(not local.is_absolute() and path.is_relative_to(root), 'research file escapes dossier')
            require(path.is_file() and path.stat().st_size<=5_000_000, 'research source file missing/oversized')
            body = path.read_bytes()
            require(hashlib.sha256(body).hexdigest()==poll['sha256'], 'research source fingerprint changed')
            questions = [(q,False) for q in poll.get('questions',[])]
            questions += [(q,True) for q in poll.get('reported_figures_not_complete_ballots',[])]
            require(questions, 'no question-level research records')
            for index,(question,incomplete) in enumerate(questions):
                try:
                    rid = scheduled_race(state,question['office'],question.get('district'),catalog)
                    reasons = []
                    start,end = poll.get('field_start'),poll.get('field_end')
                    require(start and end and start<=end<=as_of, 'research field dates invalid')
                    date.fromisoformat(start);date.fromisoformat(end)
                    release = poll.get('released_on')
                    if release is None:
                        reasons.append('release_date_not_disclosed')
                    else:
                        date.fromisoformat(release)
                        require(end<=release<=as_of, 'research release date invalid')
                    if question.get('stage') != 'general': reasons.append('general_question_not_verified')
                    if not question.get('prompt'): reasons.append('question_wording_missing')
                    if not question.get('ballot'): reasons.append('ballot_format_missing')
                    if question.get('initial_ballot') is not True: reasons.append('initial_question_not_verified')
                    sample = question.get('sample_n')
                    if type(sample) is not int or sample<=0: reasons.append('question_sample_n_missing')
                    if not question.get('sample_base'): reasons.append('question_sample_base_not_verified')
                    if (question.get('geography_state') != state or
                        question.get('geography_scope') != ('district' if question['office']=='house' else 'statewide')):
                        reasons.append('question_geography_not_verified')
                    if (question.get('population') or poll.get('population') or '').lower() not in ('lv','rv','adults'):
                        reasons.append('population_missing')
                    for field in ('mode','weighting'):
                        if not poll.get(field): reasons.append(field+'_missing')
                    if not poll.get('sponsor') and not poll.get('sponsor_statement'):
                        reasons.append('commissioner_not_disclosed')
                    answers = question.get('results_pct')
                    require(isinstance(answers,list) and len(answers)>=2, 'research answer table missing')
                    labels = []
                    for answer in answers:
                        require(isinstance(answer.get('label'),str) and answer['label'], 'research answer label missing')
                        value = answer.get('pct')
                        require(type(value) in (int,float) and math.isfinite(value) and 0<=value<=100,
                                'research invalid percentage')
                        labels.append(answer['label'])
                        if answer.get('identity_status'): reasons.append('candidate_identity_review_required')
                    require(len(set(labels))==len(labels) and sum(a['pct'] for a in answers)<=102,
                            'research duplicate answer/invalid total')
                    if incomplete: reasons.append('incomplete_reported_ballot')
                    # Full sample n, unweighted n, and oversamples are intentionally not substituted.
                    evidence = {'dossier_sha256':digest(dossier),'record_id':poll.get('id'),
                        'original_research_checked_on':dossier['checked_on'],
                        'question_index':index,'document_sha256':poll['sha256'],
                        'poll':{k:deepcopy(v) for k,v in poll.items() if k not in
                            ('questions','reported_figures_not_complete_ballots','local_file')},
                        'question':deepcopy(question)}
                    rows.append({'race_id':rid,'source_url':url,'seen_at':seen_at,
                        'kind':'research_dossier','evidence':evidence,'reasons':sorted(set(reasons))})
                except (ValueError, KeyError, TypeError, AttributeError) as exc:
                    rejected.append({'input_id':poll.get('id'),'question_index':index,'error_type':type(exc).__name__})
        except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
            rejected.append({'input_id':poll.get('id'),'error_type':type(exc).__name__})
    return rows,rejected


def priority(rid, board):
    focus = board.get('house_poll_focus',{}).get('races',{})
    if rid in focus:
        row = focus[rid]
        return {'order':0,'basis':'house_toss_up_lean_or_reviewed_caution',
                'classification':row.get('classification'),'rating_as_of':row.get('rating_as_of'),
                'within_focus_order':row.get('collection_priority',{}).get('within_focus_order',4)}
    state = rid.split(':')[1] if rid else None
    return {'order':1 if state in PRIORITY_STATES else 2 if rid else 3,
            'basis':'requested_priority_state' if state in PRIORITY_STATES else
                    'other_scheduled_race' if rid else 'race_identity_unresolved'}


def candidate_checks(version, race):
    reasons = list(version['reasons'])
    question = version['evidence']['question']; names=[]
    noncandidate = {'undecided','don\'t know','refused','someone else','other',
                    'i will not vote in this race','no answer'}
    for answer in question['results_pct']:
        label = answer['label']
        if label.casefold() in noncandidate:
            continue
        # Ask researchers for the exact reviewed name; party suffixes, spelling
        # fixes and nicknames are never fuzzy-matched into the ballot.
        name = answer.get('candidate_name',label)
        identity = race.get('candidates',{}).get(name)
        if identity is None:
            reasons.append('candidate_identity_review_required')
        else:
            names.append(identity.get('canonical_name',name))
            if answer.get('party') and answer['party'] != identity['party']:
                reasons.append('candidate_party_conflict')
    required = {race.get('candidates',{}).get(n,{}).get('canonical_name',n)
                for n in race.get('required_candidates',[])}
    if not required or not required<=set(names): reasons.append('reviewed_matchup_incomplete')
    if len(names)!=len(set(names)): reasons.append('duplicate_candidate_alias')
    return sorted(set(reasons))


def build_intake(candidates, board, as_of, checked_at, previous=None, source_health=None, rejected=()):
    require(date.fromisoformat(as_of)<=datetime.fromisoformat(checked_at.replace('Z','+00:00')).date(), 'future intake date')
    require(previous is None or (previous.get('schema')==SCHEMA and previous.get('cycle')==2026), 'previous intake schema')
    records = {row['id']:deepcopy(row) for row in (previous or {}).get('records',[])}
    require(len(records)==len((previous or {}).get('records',[])), 'duplicate previous intake ID')
    prior_ids = set(records); seen = set(); changed = set()
    for candidate in candidates:
        rid = candidate['race_id']; url = canonical_url(candidate['source_url'])
        # One review task per document/race. Multiple questions/versions stay separate below.
        key = 'intake-'+digest({'race_id':rid,'source_url':url})[:24]
        require(rid is None or rid in board['races'], 'intake race outside board')
        observed = candidate['seen_at']; datetime.fromisoformat(observed.replace('Z','+00:00'))
        require(observed[:10]<=as_of, 'future intake observation')
        version = {k:deepcopy(candidate[k]) for k in ('kind','evidence','reasons')}
        fingerprint = digest(version)
        row = records.setdefault(key, {'id':key,'race_id':rid,'source_url':url,
            'first_seen_at':observed,'last_seen_at':observed,'versions':[]})
        require(row['race_id']==rid and row['source_url']==url, 'intake identity changed')
        if not any(v['sha256']==fingerprint for v in row['versions']):
            row['versions'].append({'sha256':fingerprint,**version,'first_seen_at':observed,'last_seen_at':observed})
            if key in prior_ids: changed.add(key)
        else:
            saved = next(v for v in row['versions'] if v['sha256']==fingerprint)
            saved['last_seen_at'] = max(saved.get('last_seen_at',saved['first_seen_at']),observed)
        row['first_seen_at'] = min(row['first_seen_at'],observed)
        row['last_seen_at'] = max(row['last_seen_at'],observed)
        seen.add(key)
    for row in records.values():
        row['priority'] = priority(row['race_id'],board)
        row['collection_state'] = 'observed_this_run' if row['id'] in seen else 'carried_forward'
        row['signal_eligible'] = False
        research = [v for v in row['versions'] if v['kind']=='research_dossier']
        for version in research:
            version['review_readiness'] = candidate_checks(version,board['races'][row['race_id']])
        latest = max((v['evidence']['original_research_checked_on'] for v in research),default=None)
        ready = any(not v['review_readiness'] and v['evidence']['original_research_checked_on']==latest for v in research)
        row['ready_for_review_version_ids'] = [v['sha256'] for v in research
            if not v['review_readiness'] and v['evidence']['original_research_checked_on']==latest]
        row['status'] = ('race_identity_unresolved' if not row['race_id'] else
                         'ready_for_human_review' if ready else 'research_gaps' if research else 'primary_review_required')
        if row['race_id'] and board['races'][row['race_id']].get('phase','pre_election')!='pre_election':
            row['status'] = 'election_closed_reference'
        # Exact URL is only a hint; never mark an unreviewed new wave as already admitted.
        observations = board['races'].get(row['race_id'],{}).get('observations',[])
        row['source_url_observation_matches'] = [o['id'] for o in observations
            if o.get('source_url') and canonical_url(o['source_url'])==row['source_url']]
    def ordering(row):
        state = row['race_id'].split(':')[1] if row['race_id'] else None
        return (row['priority']['order'],row['priority'].get('within_focus_order',4),
                PRIORITY_STATES.index(state) if state in PRIORITY_STATES else len(PRIORITY_STATES),
                row['first_seen_at'],row['id'])
    rows = sorted(records.values(),key=ordering)
    focus = set(board.get('house_poll_focus',{}).get('races',{}))
    found_focus = {r['race_id'] for r in rows if r['race_id'] in focus}
    coverage = {}
    for office in ('governor','senate','house'):
        selected = [r for r in board['races'].values() if r.get('office')==office]
        coverage[office] = {str(days):sum(any(o.get('aggregation_eligibility',{}).get('eligible') is True
            and 0<=(date.fromisoformat(as_of)-date.fromisoformat(o['field_end'])).days<days
            for o in r.get('observations',[])) for r in selected) for days in (7,14)}
    return {'schema':SCHEMA,'cycle':2026,'as_of':as_of,'checked_at':checked_at,
        'status':'partial' if rejected or any(h.get('status') not in ('ok','fetched') for h in (source_health or {}).values()) else 'ok',
        'records':rows,'source_health':deepcopy(source_health or {}),'rejected_inputs':list(rejected),
        'summary':{'candidate_documents':len(rows),'new_documents':len(set(records)-prior_ids),
            'changed_documents':len(changed),'carried_forward_documents':len(set(records)-seen),
            'priority_house_documents':sum(r['priority']['order']==0 for r in rows),
            'focus_races_total':len(focus),'focus_races_with_candidates':len(found_focus),
            'focus_races_without_candidates':sorted(focus-found_focus),
            'by_status':dict(Counter(r['status'] for r in rows)),
            'by_state':dict(Counter(r['race_id'].split(':')[1] for r in rows if r['race_id'])),
            'recent_poll_race_coverage':coverage,'signal_eligible_documents':0},
        'limitations_ko':'문서 검토 대기열이며 조사 건수·기관 등급·당선 전망이 아닙니다. 수치와 파일 무결성 검사만으로 원문 대조·후보·표본·의뢰자 검토를 승인하지 않습니다.'}


def research_tasks(intake, board):
    jobs = []
    for row in intake['records']:
        rid = row['race_id']
        if not rid or board['races'].get(rid,{}).get('phase','pre_election')!='pre_election':
            continue
        race = board['races'].get(rid,{})
        jobs.append({'intake_id':row['id'],'race_id':rid,'state':rid.split(':')[1],
            'source_url':row['source_url'],'priority':deepcopy(row['priority']),
            'reviewed_candidates':deepcopy(race.get('candidates',{})),
            'source_url_observation_matches':row['source_url_observation_matches'],
            'input_version_sha256':[v['sha256'] for v in row['versions']],
            'required_research_fields':['original_document','sha256','pollster','commissioner',
                'field_start','field_end','released_on','population','question_sample_n','sample_base',
                'geography','question_wording','initial_ballot','mode','weighting','candidate_results'],
            'output_schema':'usa_state_research_dossier_v1','signal_eligible':False})
    return {'schema':'usa_poll_research_tasks_v1','cycle':intake['cycle'],'as_of':intake['as_of'],
            'jobs':jobs,'unresolved_race_intake_ids':[r['id'] for r in intake['records'] if not r['race_id']],
            'note_ko':'원문 조사 작업 목록. 기존 후보명·정당도 기준일을 확인하고 원문 표기는 별도로 보존합니다. 승인 또는 집계 입력이 아닙니다.'}


def attach_saved_intake(board, previous, checkpoint):
    """Existing Actions downloads this discovery sibling with the captured inputs."""
    from .polls import read
    old = (previous or {}).get('poll_intake')
    if checkpoint is None:
        if old: board['poll_intake'] = deepcopy(old)
        return
    path = Path(checkpoint).with_suffix('.discovery.json')
    try:
        require(path.exists(), 'intake discovery artifact unavailable')
        report = read(path)
        require(report.get('schema')=='usa_poll_source_discovery_v1'
                and report.get('cycle')==2026 and report['as_of']==board['as_of'], 'intake capture date/schema mismatch')
        require(report.get('provider_comparison',{}).get('captured_at')==board['fetched_at'], 'intake provider capture mismatch')
        capture = read(Path(checkpoint))
        require(report['provider_comparison'].get('provider_rows_sha256')==digest(capture['provider_rows']),
                'intake provider input mismatch')
        catalog = read(Path(__file__).resolve().parents[1]/'config/usa_polls/targets_2026.json')
        candidates,rejected = discovery_candidates(report,catalog)
        for result in report.get('research_intake',[]):
            candidates.extend(result['candidates']); rejected.extend(result['rejected_inputs'])
        board['poll_intake'] = build_intake(candidates,board,board['as_of'],report['captured_at'],old,
                                          report.get('source_health',{}),rejected)
        board['poll_intake_health'] = {'status':'ok','artifact_captured_at':report['captured_at']}
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        if old: board['poll_intake'] = deepcopy(old)
        board['poll_intake_health'] = {'status':'carried_forward' if old else 'unavailable',
            'attempted_at':board['fetched_at'],'error_type':type(exc).__name__}
