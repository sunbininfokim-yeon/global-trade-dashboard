#!/usr/bin/env python3
"""Collect supplemental public discovery links without touching published data."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from election_watch.polls import atomic, read
from election_watch.poll_source_discovery import collect_270, annotate_provider_links

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--provider-capture', type=Path)
    args = parser.parse_args()
    catalog = read(ROOT/'config/usa_polls/targets_2026.json')
    names = {state: entry['name'] for state, entry in catalog['states'].items()}
    result = collect_270(catalog['cycle'], args.as_of, datetime.now(timezone.utc).isoformat(), names)
    result['provider_comparison'] = {'status': 'not_available'}
    if args.provider_capture and args.provider_capture.exists():
        try:
            captured = read(args.provider_capture)
            if captured.get('schema') not in ('usa_poll_provider_capture_v1', 'usa_poll_run_capture_v1'):
                raise ValueError('unsupported provider checkpoint')
            annotate_provider_links(result, captured['provider_rows'], captured['captured_at'])
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            # A primary-provider failure must not discard secondary discovery.
            result['provider_comparison'] = {'status': 'unavailable', 'error_type': type(exc).__name__}
    atomic(args.output, result)
    print(result['summary'])
    if result['status'] != 'ok':
        print('::warning::Supplemental poll discovery is partial; see source_health, not a polling publication failure')
    return 0 if result['records'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
