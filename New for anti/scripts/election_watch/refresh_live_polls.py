#!/usr/bin/env python3
"""Refresh selected US polls; preserve previous data on transport/schema failure."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from election_watch.polls import read, atomic
from election_watch.live_polls import (apply_watchlist, build_live, close_finished_races,
                                      fetch_polls, poll_history, validated_results)
from election_watch.poll_priorities import apply_priorities, attach_coverage, load_finance_links
from election_watch.seat_scenarios import build_scenarios, held_scenarios
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_ballots import fetch_florida
from election_watch.poll_gaps import attach_gaps, refresh_gap_lifecycle
from election_watch.poll_house_focus import apply_house_focus, attach_house_focus, refresh_house_focus_lifecycle
from election_watch.superpac import SourceError

ROOT = Path(__file__).resolve().parent


def publish_scenarios(board, args, checked, health=None):
    # Forecast validation must not discard successfully fetched polling data.
    try:
        forecast = build_scenarios(board, read(args.election_board), read(args.scenario_policy),
                                   args.as_of, checked, health)
        status = {'status': 'ok'}
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        forecast = held_scenarios(args.as_of, checked, type(exc).__name__)
        status = {'status': 'hold', 'error_type': type(exc).__name__}
    atomic(args.output.with_name('usa_midterms_forecast_v1.json'), forecast)
    return status


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--policy', type=Path, default=ROOT/'config/usa_polls/live_2026.json')
    p.add_argument('--watchlist', type=Path, default=ROOT/'config/usa_polls/watchlist_2026.json')
    p.add_argument('--priorities', type=Path, default=ROOT/'config/usa_polls/priorities_2026.json')
    p.add_argument('--districts', type=Path, default=ROOT.parent.parent/'public/data/congressional_districts/USA')
    p.add_argument('--finance-index', type=Path, default=ROOT.parent.parent/'public/data/usa_election_finance_index_v1.json')
    p.add_argument('--quality-reviews', type=Path, default=ROOT/'config/usa_polls/quality_reviews_2026.json')
    p.add_argument('--governor-matchups', type=Path, help='Reviewed governor roster; the production policy uses its cycle snapshot by default')
    p.add_argument('--results', type=Path, default=ROOT/'config/usa_polls/results_2026.json')
    p.add_argument('--output', type=Path, default=ROOT.parent.parent/'public/data/usa_election_live_polls_v1.json')
    p.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    p.add_argument('--scenario-policy', type=Path, default=ROOT/'config/usa_polls/seat_scenarios_2026.json')
    p.add_argument('--election-board', type=Path, default=ROOT.parent.parent/'public/data/elections_board_v1.json')
    p.add_argument('--input', type=Path, help='Replay saved provider response for testing; marked as replay')
    p.add_argument('--target-catalog', type=Path, help='Reviewed nationwide scheduled election universe')
    p.add_argument('--ballot-reviews', type=Path, help='Reviewed general ballot identities for poll admission')
    p.add_argument("--house-focus", type=Path, help="House Lean/Toss-Up review priority policy")
    p.add_argument("--ratings", type=Path, default=ROOT.parent.parent/"public/data/usa_election_ratings_review_v1.json")
    args = p.parse_args()
    production_policy = args.policy.resolve() == (ROOT/'config/usa_polls/live_2026.json').resolve()
    target_catalog = args.target_catalog or (ROOT/'config/usa_polls/targets_2026.json' if production_policy else None)
    ballot_reviews = args.ballot_reviews or (ROOT/'config/usa_polls/ballot_reviews_2026.json' if production_policy else None)
    house_focus = args.house_focus or (ROOT/'config/usa_polls/house_focus_2026.json' if production_policy else None)
    governor_matchups = args.governor_matchups
    if governor_matchups is None and production_policy:
        governor_matchups = ROOT/'config/governor_matchups/2026.json'
    checked = datetime.now(timezone.utc).isoformat()
    health = args.output.with_name('usa_election_live_polls_status_v1.json')
    ballot_health = {'status': 'not_configured'}
    ballots = None
    def refresh_ballots():
        nonlocal ballot_health
        if not ballots:
            return
        ballot_health = {'status': 'reviewed_snapshot', 'reviewed_on': ballots['reviewed_on']}
        if not args.input:
            try:
                florida = fetch_florida(args.as_of)
                for rid, review in florida['races'].items():
                    # Only preserve explicit aliases for exactly the same agency
                    # candidate; never infer a nickname after a withdrawal.
                    previous = {c['name']: c for c in ballots['races'].get(rid, {}).get('candidates', [])}
                    for candidate in review['candidates']:
                        aliases = previous.get(candidate['name'], {}).get('poll_name_aliases')
                        if aliases:
                            candidate['poll_name_aliases'] = aliases
                ballots['races'].update(florida['races'])
                ballot_health = {'status': 'ok', 'source_url': florida['source_url'],
                    'source_sha256': florida['source_sha256'], 'checked_on': florida['checked_on'], 'races': 30}
            except (OSError, ValueError, TypeError, KeyError) as exc:
                ballot_health = {'status': 'carried_forward', 'error_type': type(exc).__name__,
                    'original_reviewed_on': ballots['reviewed_on'], 'carried_at': checked}
    def selected_policy():
        policy = apply_priorities(apply_watchlist(read(args.policy), read(args.watchlist)),
                                  read(args.priorities), args.districts, args.as_of)
        if governor_matchups and governor_matchups.exists():
            policy = apply_matchups(policy, read(governor_matchups), args.as_of)
        if target_catalog:
            if ballots is None:
                raise ValueError('target catalog requires ballot review contract')
            policy = apply_targets(policy, read(target_catalog), ballots, args.as_of)
        if house_focus:
            try:
                policy = apply_house_focus(policy, read(args.ratings), read(args.election_board), read(house_focus), args.as_of)
                policy['house_poll_focus_health'] = {'status': 'ok', 'checked_as_of': args.as_of}
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                # Review priority failures must not discard good polling data.
                policy['house_poll_focus_health'] = {'status': 'hold', 'checked_as_of': args.as_of, 'error_type': type(exc).__name__}
        return policy
    try:
        ballots = read(ballot_reviews) if ballot_reviews else None
        policy = selected_policy()
        quality = read(args.quality_reviews)
        if quality['schema'] != 'usa_poll_quality_reviews_v1' or quality['cycle'] != policy['cycle']:
            raise ValueError('quality review schema/cycle')
        rows, url = (read(args.input), 'replay') if args.input else fetch_polls(policy['cycle'], args.as_of)
        refresh_ballots()
        policy = selected_policy()
        policy['quality_reviews'] = quality['reviews']
        board = build_live(rows, policy, read(args.results), args.as_of, checked, url)
        try:
            finance = load_finance_links(args.finance_index, policy['cycle'])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            finance = {'status': 'hold', 'error_type': type(exc).__name__, 'races': {}}
        attach_coverage(board, rows, policy, finance)
        attach_house_focus(board, policy)
        if target_catalog:
            attach_gaps(board, finance)
            board['ballot_source_health'] = ballot_health
        history = poll_history(rows, policy, args.as_of)
        if args.input:
            board['source_status'] = 'replay'
        archive_path = args.output.with_name(f'usa_election_poll_history_{policy["cycle"]}.json')
        atomic(archive_path, history)
        atomic(args.output, board)
        forecast_status = publish_scenarios(board, args, checked)
        atomic(health, {'checked_at': checked, 'status': board['source_status'], 'as_of': args.as_of,
                        'seat_scenario': forecast_status, 'ballot_source': ballot_health})
        print(board['coverage'])
        print({d: {s: sum(r['windows'][d]['status'] == s for r in board['races'].values())
                   for s in ('poll_lead','single_poll_lead','no_recent_poll','tie','unknown_leader_party')} for d in ('7','14')})
        if forecast_status['status'] != 'ok':
            print('Seat scenario held:', forecast_status['error_type'])
            return 1
    except Exception as exc:
        # Official outcomes are independent of the poll transport. If the API
        # fails, still accept a newly reviewed result without refreshing polls.
        try:
            existing = read(args.output)
            policy = selected_policy()
            confirmed = validated_results(read(args.results), policy, args.as_of)
            changed = close_finished_races(existing, policy, confirmed, args.as_of)
            if changed:
                existing['coverage']['displayed_observations'] = sum(
                    len(r.get('observations', [])) for r in existing.get('races', {}).values())
                existing['source_status'] = 'error_stale'
                refresh_gap_lifecycle(existing)
                refresh_house_focus_lifecycle(existing)
                atomic(args.output, existing)
            # Recompute conditional counts without stale polling signals.
            publish_scenarios(existing, args, checked, {'status': 'error'})
        except (OSError, ValueError, KeyError, TypeError, SourceError):
            pass
        atomic(health, {'checked_at': checked, 'status': 'error', 'error_type': type(exc).__name__,
                        'note_ko': '수집 실패. 마지막 정상 자료를 보존하며 지도 색상은 중립 처리합니다.'})
        print('Poll refresh failed:', type(exc).__name__)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
