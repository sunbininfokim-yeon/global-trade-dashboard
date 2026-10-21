#!/usr/bin/env python3
"""Collect supplemental public discovery links without touching published data."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from election_watch.polls import atomic, read, digest
from election_watch.poll_source_discovery import collect_270, annotate_provider_links
from election_watch.poll_additional_discovery import collect_additional, extend_report
from election_watch.poll_primary_discovery import collect_primary
from election_watch.poll_intake import research_candidates

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--provider-capture', type=Path)
    parser.add_argument('--research-dossier', type=Path, action='append', default=[],
                        help='Cursor dossier plus sibling raw/; reviewed as pending input, never automatic admission')
    args = parser.parse_args()
    catalog = read(ROOT/'config/usa_polls/targets_2026.json')
    names = {state: entry['name'] for state, entry in catalog['states'].items()}
    result = collect_270(catalog['cycle'], args.as_of, datetime.now(timezone.utc).isoformat(), names)
    result = extend_report(result, collect_additional(catalog['cycle'], args.as_of,
        datetime.now(timezone.utc).isoformat(), names))
    primary = collect_primary(catalog,args.as_of,datetime.now(timezone.utc).isoformat())
    result = extend_report(result,{**primary,'commentary':result.get('commentary',[])})
    paths = sorted(set(args.research_dossier) | set((ROOT/'research'/str(catalog['cycle'])).glob('*/*_records.json')))
    result['research_intake'] = []
    for path in paths:
        try:
            dossier = read(path)
            candidates,rejected = research_candidates(dossier,path.parent,catalog,args.as_of,result['captured_at'])
            result['research_intake'].append({'source_file':path.name,'state':dossier['state'],
                'candidates':candidates,'rejected_inputs':rejected})
        except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
            result['research_intake'].append({'source_file':path.name,'candidates':[],
                'rejected_inputs':[{'input_id':path.name,'error_type':type(exc).__name__}]})
    result['provider_comparison'] = {'status': 'not_available'}
    if args.provider_capture and args.provider_capture.exists():
        try:
            captured = read(args.provider_capture)
            if captured.get('schema') not in ('usa_poll_provider_capture_v1', 'usa_poll_run_capture_v1'):
                raise ValueError('unsupported provider checkpoint')
            annotate_provider_links(result, captured['provider_rows'], captured['captured_at'])
            result['provider_comparison']['provider_rows_sha256'] = digest(captured['provider_rows'])
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            # A primary-provider failure must not discard secondary discovery.
            result['provider_comparison'] = {'status': 'unavailable', 'error_type': type(exc).__name__}
    atomic(args.output, result)
    print(result['summary'])
    if result['status'] != 'ok':
        print('::warning::Supplemental poll discovery is partial; see source_health, not a polling publication failure')
    return 0 if result['records'] or any(r['candidates'] for r in result['research_intake']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
