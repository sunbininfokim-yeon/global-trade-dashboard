#!/usr/bin/env python3
"""Refresh sourced USA House context; publish only USA fields in the existing board."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen
from build_superpac import PUBLIC, ROOT, atomic_json
from election_watch.superpac import now
from election_watch.congress_context import MEMBERS_URL, VACANCIES_URL, house_context, swing_seats


def apply_board(board, congress):
    usa = next(c for c in board['countries'] if c.get('iso3') == 'USA')
    ui = usa['ui_ready']['congress']
    for key in ('summary', 'vacancies', 'swing_seats', 'context_coverage'):
        ui[key] = congress[key]
    ui['house_members'] = [m for m in congress['members'] if m['chamber'] == 'house']
    usa['legislature_live'].update(summary=congress['summary'], members=congress['members'], source=congress['source'])
    from build_board import build_usa_state_drilldown, load_extracted
    usa['ui_ready']['state_drilldown'] = build_usa_state_drilldown(congress, load_extracted('usa_governors.json'), load_extracted('usa_state_legislatures.json'), load_extracted('usa_state_officials.json'), load_extracted('race_progress_usa_v1.json'))
    return board


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--member-xml', type=Path)
    p.add_argument('--vacancies-html', type=Path)
    p.add_argument('--public', type=Path, default=PUBLIC)
    args = p.parse_args()
    xml = args.member_xml.read_bytes() if args.member_xml else urlopen(MEMBERS_URL, timeout=45).read()
    html = args.vacancies_html.read_text() if args.vacancies_html else urlopen(VACANCIES_URL, timeout=45).read().decode()
    context = house_context(xml, html)
    extracted = ROOT / 'config/extracted/usa_congress.json'
    old = json.loads(extracted.read_text())
    history = json.loads((ROOT / 'config/usa_election_history_verified_v1.json').read_text())
    senators = [m for m in old['members'] if m['chamber'] == 'senate']
    prior_order = {m['bioguideId']: i for i,m in enumerate(old['members'])}
    old['members'] = sorted(context['members'] + senators, key=lambda m: prior_order.get(m['bioguideId'], 100000))
    old['summary'].update(context['house_summary'], members_total_including_house_delegates=len(old['members']))
    old['vacancies'] = context['vacancies']
    old['swing_seats'] = swing_seats(history)
    old['context_coverage'] = {'checked_at': now(), 'house_source_published_on': context['house_source_published_on'],
        'vacancies': 'house_complete_senate_not_refreshed', 'senate_roster_as_of': old['as_of'],
        'swing_seats': 'partial_verified_examples', 'history_coverage': history['coverage'],
        'limitations_ko': ['경합은 예측·접전 득표율이 아닌 사용자 정의 이력 조건입니다.',
            '전국 하원 대선 교차투표·재획정 전후 선거 이력은 미확보. 목록에 없다고 비경합을 뜻하지 않습니다.',
            '상원 교차투표는 2024년 당선 의석 기준이며 2026년 선거 대상이라는 뜻은 아닙니다.']}
    old['source'].update(house_members=MEMBERS_URL, house_vacancies=VACANCIES_URL)
    board_path = args.public / 'elections_board_v1.json'
    board = apply_board(json.loads(board_path.read_text()), old)
    atomic_json(extracted, old, indent=2)
    atomic_json(board_path, board, indent=2)
    print(json.dumps({'house_vacancies': len(old['vacancies']), 'swing_seats': len(old['swing_seats'])}))

if __name__ == '__main__': main()
