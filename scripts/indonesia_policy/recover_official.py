"""Collect a bounded, curator-reviewed official mirror pack; no DB, AI or mail.

Keep this separate from live scheduler checkpoints. A successful mirror must
pass the same identity/final-text checks as its original. A discovered link or
metadata page never counts as a recovered original.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from collect import collect, official_url
from sync_reviewed import atomic_json

REPO = Path(__file__).resolve().parents[2]


def urls(entry):
    alternatives = entry.get('official_alternatives', [])
    if not isinstance(alternatives, list):
        raise ValueError('invalid official alternatives')
    values = [entry['url'], *alternatives]
    if (not 1 <= len(values) <= 3 or any(not isinstance(u, str) or not official_url(u) for u in values)
            or len(set(values)) != len(values)):
        raise ValueError('expected at most three distinct official URLs')
    return values


def recover(entries, output, *, collector=collect, pause=time.sleep, initial_cooldowns=None):
    output = Path(output).resolve()
    if output.exists() or output == REPO or REPO in output.parents:
        raise ValueError('use a new output directory outside repository')
    if not 1 <= len(entries) <= 10 or len({e['document_id'] for e in entries}) != len(entries):
        raise ValueError('expected 1..10 distinct reviewed document identities')
    # Validate the whole pack before making any source requests.
    for entry in entries:
        urls(entry)
        if not entry.get('identity_phrases'):
            raise ValueError('reviewed identity phrases required')
    output.mkdir(parents=True, mode=0o700)
    raw = output / 'raw'
    raw.mkdir(mode=0o700)
    result = dict(checked_at=datetime.now(timezone.utc).isoformat(), documents=[], failures=[], source_attempts=[])
    blocked = {host for host, until in (initial_cooldowns or {}).items() if until > time.time()}
    for entry in entries:
        recovered = False
        for url in urls(entry):
            host = urlparse(url).hostname
            attempt = dict(document_id=entry['document_id'], url=url)
            if host in blocked:
                attempt.update(outcome='deferred', reason='host_deferred_earlier_in_run')
            else:
                try:
                    doc = collector({**entry, 'url': url}, raw, blocked)
                    if (doc.get('document_id') != entry['document_id'] or doc.get('country_code') != 'IDN'
                            or doc.get('legal_status') != 'unverified'):
                        raise ValueError('collector identity invariant failed')
                    complete = (doc.get('content_kind') == 'official_text'
                                and doc.get('body_status') == 'extracted'
                                and doc.get('text_truncated') is False)
                    attempt.update(outcome='recovered' if complete else 'held', reason=doc.get('body_status', 'incomplete_text'))
                    if doc.get('body_fetch_blocked_host'):
                        blocked.add(doc['body_fetch_blocked_host'])
                    if complete:
                        result['documents'].append(doc)
                        recovered = True
                    else:
                        blocked.add(host)
                except Exception as error:
                    status = getattr(getattr(error, 'response', None), 'status_code', None)
                    attempt.update(outcome='failed', reason=str(error)[:300], http_status=status)
                    # No alternate path on a blocked/unavailable host in this run.
                    if status in (403, 429, 503) or any(x in str(error).lower() for x in ('blocked', 'maintenance')):
                        blocked.add(host)
            result['source_attempts'].append(attempt)
            atomic_json(output / 'collection.json', result)
            if recovered:
                break
            pause(2)
        if not recovered:
            result['failures'].append(dict(document_id=entry['document_id'], url=entry['url'], error='complete_official_text_not_recovered'))
        atomic_json(output / 'collection.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--cooldown-file', required=True, type=Path,
                        help='Current scheduler active-run.json or reviewed status.json; never clear a live cooldown')
    args = parser.parse_args()
    cooldowns = json.loads(args.cooldown_file.read_text())['cooldowns']
    if not isinstance(cooldowns, dict) or any(not isinstance(h, str) or type(t) not in (int, float) for h, t in cooldowns.items()):
        parser.error('invalid shared cooldown snapshot')
    result = recover(json.loads(args.manifest.read_text()), args.output_dir, initial_cooldowns=cooldowns)
    print(json.dumps(dict(recovered=len(result['documents']), held=len(result['failures']),
                         attempts=len(result['source_attempts']), database_writes=False, ai_calls=0)))


if __name__ == '__main__':
    main()
