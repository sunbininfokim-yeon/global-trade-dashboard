#!/usr/bin/env python3
"""Lower-confidence poll layer: rows the board holds for review, shown and counted with a label.

The reviewed board stays the source of truth. This layer takes the provider rows
the board did not admit (review queue), maps their answers onto the race's
reviewed candidate list, and writes a separate read model that the UI shows as
"원문 미검토" and may count where the reviewed board has no 14-day verdict.

Board observations that are on the board but excluded from the 14-day count
(reference only, e.g. release review pending) are counted here too, except
ranked-choice first-preference rows. Never used: campaign internals, rows whose provider values conflict with a
primary release, rows before the race's general period, non-candidate ballots.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re

from election_watch.polls import read, atomic
from election_watch.state_inputs import packets

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parent.parent/'public/data'
OUTPUT = 'usa_election_unreviewed_polls_v1.json'
WINDOW_DAYS = 14

SKIP_REASONS = {'date_order_or_future', 'generic_party_ballot_not_named_race'}
TIERS = {
    'reference_reviewed': {'label_ko': '참고용(검토 보드 수록·집계 제외)', 'counted': True},
    'unreviewed': {'label_ko': '원문 미검토', 'counted': True},
    'partisan_unreviewed': {'label_ko': '당파 후원·원문 미검토', 'counted': True},
    'campaign_internal': {'label_ko': '캠프 내부 조사', 'counted': False},
    'provider_conflict': {'label_ko': '원문과 수치 불일치', 'counted': False},
}


def _key(name):
    name = re.sub(r'[^a-z ]', '', (name or '').lower().replace('.', ' '))
    return [p for p in name.split() if p not in ('jr', 'sr', 'ii', 'iii')]


def map_answers(answers, candidates):
    """Exact or alias name first, then a unique last-name match. Unknown stays unknown."""
    by_last = {}
    for name, info in candidates.items():
        parts = _key(name)
        if parts:
            by_last.setdefault(parts[-1], set()).add((info.get('canonical_name') or name, info.get('party')))
    out = []
    for a in answers:
        info = candidates.get(a['choice'])
        if info:
            out.append({'name': info.get('canonical_name') or a['choice'], 'pct': a['pct'], 'party': info.get('party'), 'matched': 'name'})
            continue
        parts = _key(a['choice'])
        hits = by_last.get(parts[-1], set()) if parts else set()
        if len(hits) == 1:
            name, party = next(iter(hits))
            out.append({'name': name, 'pct': a['pct'], 'party': party, 'matched': 'last_name'})
        else:
            out.append({'name': a['choice'], 'pct': a['pct'], 'party': None, 'matched': None})
    return out


def tier_for(row, held):
    if row.get('internal'):
        return 'campaign_internal'
    if 'conflict' in held.get('reason', ''):
        return 'provider_conflict'
    if row.get('partisan'):
        return 'partisan_unreviewed'
    return 'unreviewed'


def leader(answers):
    """Leading party between the best Democratic/independent and Republican answers."""
    best = {}
    for a in answers:
        party = {'GOP': 'REP'}.get(a['party'], a['party'])
        if party in ('DEM', 'REP', 'IND') and a['pct'] is not None and a['pct'] > best.get(party, -1):
            best[party] = a['pct']
    if 'REP' not in best or not ({'DEM', 'IND'} & set(best)):
        return None
    left = max(((p, v) for p, v in best.items() if p != 'REP'), key=lambda x: x[1])
    margin = left[1] - best['REP']
    return {'party': left[0] if margin > 0 else 'REP' if margin < 0 else None, 'margin': round(margin, 1)}


def combined_verdict(race, polls, as_of):
    """Latest poll per pollster in the 14-day window, reviewed first, then counted unreviewed."""
    start = (date.fromisoformat(as_of) - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    included = set((race.get('windows', {}).get(str(WINDOW_DAYS)) or {}).get('included_ids') or [])
    latest = {}

    def offer(key, entry):
        prev = latest.get(key)
        if (not prev or (entry['reviewed'], entry['field_end'], entry['population'] == 'lv')
                > (prev['reviewed'], prev['field_end'], prev['population'] == 'lv')):
            latest[key] = entry
    for o in race.get('observations', []):
        if o['id'] in included and (o.get('field_end') or '') >= start:
            lead = leader([{'party': a.get('party'), 'pct': a.get('pct')} for a in o.get('answers', [])])
            if lead:
                offer((o.get('pollster_group') or o['pollster']).lower(), {'id': o['id'], 'reviewed': True,
                      'field_end': o['field_end'], 'population': o.get('population'), **lead})
    for p in polls:
        if TIERS[p['tier']]['counted'] and p['field_end'] >= start and p['lead']:
            offer(p['pollster'].lower(), {'id': p['id'], 'reviewed': False, 'field_end': p['field_end'],
                                          'population': p['population'], **p['lead']})
    entries = list(latest.values())
    counts = {}
    for e in entries:
        counts[e['party'] or 'TIE'] = counts.get(e['party'] or 'TIE', 0) + 1
    parties = sorted(((n, p) for p, n in counts.items() if p != 'TIE'), reverse=True)
    if not entries:
        status, party = 'no_recent_poll', None
    elif not parties or (len(parties) > 1 and parties[0][0] == parties[1][0]):
        status, party = 'tie', None
    else:
        party = parties[0][1]
        status = 'single_poll_lead' if len(entries) == 1 else 'poll_lead' if len(parties) == 1 else 'mixed_lead'
    return {'status': status, 'party': party, 'from': start, 'through': as_of, 'pollster_count': len(entries),
            'lead_counts': counts, 'unreviewed_ids': sorted(e['id'] for e in entries if not e['reviewed']),
            'reviewed_ids': sorted(e['id'] for e in entries if e['reviewed'])}


def build(board, provider_rows, generated_at):
    as_of = board['as_of']
    rows = {}
    for r in provider_rows:
        rows.setdefault(r['id'], r)
    races = {}
    for held in board.get('review_queue', []):
        race = board['races'].get(held.get('race_id'))
        raw = rows.get(held['id'])
        if not race or not raw or held.get('reason') in SKIP_REASONS:
            continue
        if (raw.get('end_date') or '') < (race.get('general_from') or '2026-09-01') or raw['end_date'] > as_of:
            continue
        answers = map_answers(raw.get('answers', []), race.get('candidates') or {})
        poll = {'id': raw['id'], 'pollster': raw.get('pollster') or '', 'field_start': raw.get('start_date'),
                'field_end': raw['end_date'], 'population': raw.get('population'), 'sample_n': raw.get('sample_size'),
                'sponsors': raw.get('sponsors') or [], 'partisan': raw.get('partisan'), 'internal': bool(raw.get('internal')),
                'source_url': raw.get('url'), 'held_reason': held.get('reason'), 'tier': tier_for(raw, held),
                'answers': answers, 'lead': leader(answers)}
        races.setdefault(held['race_id'], []).append(poll)
    for rid, race in board['races'].items():
        for o in race.get('observations', []):
            reasons = (o.get('aggregation_eligibility') or {}).get('reasons') or []
            if (o.get('aggregation_eligibility') or {}).get('eligible') or not o.get('answers') or any('ranked_choice' in r for r in reasons):
                continue
            if (o.get('field_end') or '') < (race.get('general_from') or '2026-09-01'):
                continue
            c = o.get('commissioning') or {}
            answers = [{'name': a.get('name'), 'pct': a.get('pct'), 'party': a.get('party'), 'matched': 'board'} for a in o['answers']]
            races.setdefault(rid, []).append({'id': o['id'], 'pollster': o.get('pollster') or '', 'field_start': o.get('field_start'),
                'field_end': o['field_end'], 'population': o.get('population'), 'sample_n': o.get('sample_n'),
                'sponsors': o.get('sponsors') or [], 'partisan': c.get('partisan'), 'internal': bool(c.get('internal')),
                'source_url': o.get('source_url'), 'held_reason': ','.join(reasons) or 'reference_only',
                'tier': 'campaign_internal' if c.get('internal') else 'reference_reviewed', 'answers': answers, 'lead': leader(answers)})
    out = {}
    for rid, race in board['races'].items():
        polls = sorted(races.get(rid, []), key=lambda p: (p['field_end'], p['id']), reverse=True)
        if not polls:
            continue
        out[rid] = {'race_id': rid, 'state': race.get('state'), 'office': race.get('office'),
                    'district': race.get('district'), 'polls': polls,
                    'combined_14': combined_verdict(race, polls, as_of)}
    return {'schema': 'usa_election_unreviewed_polls_v1', 'as_of': as_of, 'generated_at': generated_at,
            'board_fetched_at': board.get('fetched_at'), 'window_days': WINDOW_DAYS, 'tiers': TIERS,
            'basis_ko': ('검토 보드가 보류한 공급자(VoteHub) 조사를 후보 명부에 맞춰 붙인 낮은 신뢰도 층입니다. '
                         '원문 대조 전 수치이며, 검토 보드에 14일 판정이 없을 때만 전망에 참고 반영합니다. '
                         '캠프 내부 조사와 원문 불일치 행은 표시만 하고 세지 않습니다.'),
            'race_count': len(out), 'poll_count': sum(len(r['polls']) for r in out.values()), 'races': out}


def provider_rows_from(checkpoint):
    rows = list(read(checkpoint).get('provider_rows', [])) if checkpoint else []
    for packet in packets():
        rows += packet.get('capture', {}).get('provider_records', [])
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', type=Path, help='refresh_live_polls capture with provider_rows')
    p.add_argument('--provider-json', type=Path, help='raw provider row list (local replay)')
    p.add_argument('--public', type=Path, default=PUBLIC)
    args = p.parse_args()
    board = read(args.public/'usa_election_live_polls_v1.json')
    rows = provider_rows_from(args.checkpoint)
    if args.provider_json:
        rows = list(read(args.provider_json)) + rows
    data = build(board, rows, datetime.now(timezone.utc).isoformat())
    atomic(args.public/OUTPUT, data)
    print({'saved': OUTPUT, 'races': data['race_count'], 'polls': data['poll_count']})


if __name__ == '__main__':
    main()
