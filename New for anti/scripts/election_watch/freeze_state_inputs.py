#!/usr/bin/env python3
"""Move temporary reviewed catalog edits into one state packet, then restore catalogs.

Run after refresh_state_polls.py --packet. Unowned/global edits fail before any
write. Platform code/registry changes belong in a separate integration PR.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
from election_watch.polls import atomic
from election_watch.state_inputs import CONFIG, CATALOGS, digest, validate_packet


def make_operations(before, after, file, state, ids):
    operations = []
    def owned(path, value):
        return len(path) == 2 and (
            path[0] == 'races' and path[1].startswith(f'USA:{state}:') or
            path[0] in ('states', 'contests') and path[1] == state or
            path[0] in ('reviews', 'excluded_records', 'excluded_record_reviews') and path[1] in ids or
            path[0] == 'source_snapshots' and isinstance(value, dict) and value.get('state') == state)
    def walk(old, new, path, old_exists=True, new_exists=True):
        if old_exists == new_exists and old == new: return
        if owned(path, new if new_exists else old):
            operations.append({'file':file, 'path':path, 'action':'set' if new_exists else 'delete',
                'before_exists':old_exists, 'before_sha256':digest(old) if old_exists else None,
                **({'value':new} if new_exists else {})})
        elif isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(old.keys() | new.keys()):
                walk(old.get(key), new.get(key), path+[key], key in old, key in new)
        elif isinstance(old, list) and isinstance(new, list) and len(path) == 1:
            for action, values in [('remove_item', [v for v in old if v not in new]),
                                   ('append_item', [v for v in new if v not in old])]:
                for value in values:
                    if not isinstance(value, dict) or value.get('state') != state:
                        raise ValueError('unowned state collection edit: ' + file)
                    operations.append({'file':file, 'path':path, 'action':action, 'value':value})
        else: raise ValueError('shared/unowned catalog edit: ' + file + '/' + '/'.join(path))
    walk(before, after, [])
    return operations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True)
    parser.add_argument('--base-ref', default='HEAD')
    args = parser.parse_args()
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
    path = CONFIG/f'state_evidence/2026/{args.state}.json'
    packet = json.loads(path.read_text())
    ids = {r['id'] for r in packet['capture']['provider_records'] + packet['capture']['primary_records']}
    restore = {}; operations = []
    for file in sorted(CATALOGS):
        target = CONFIG/file; relative = target.relative_to(root).as_posix()
        before = json.loads(subprocess.check_output(['git', 'show', args.base_ref+':'+relative]))
        after = json.loads(target.read_text())
        if before != after:
            operations += make_operations(before, after, file, args.state, ids)
            restore[target] = before
    # Existing packet operations remain authoritative for previously sharded
    # states. Replacing an existing review is an explicit packet edit.
    existing = {(o['file'], tuple(o['path'])) for o in packet['config_operations']}
    if any((o['file'], tuple(o['path'])) in existing for o in operations):
        raise ValueError('edit the existing state packet explicitly; review replacement held')
    packet['config_operations'] += operations
    names = {s:d['name'] for s,d in json.loads((CONFIG/'usa_polls/targets_2026.json').read_text())['states'].items()}
    validate_packet(packet, names)
    atomic(path, packet)
    for target, before in restore.items(): atomic(target, before)
    print({'state':args.state, 'frozen_operations':len(operations), 'shared_catalogs_restored':len(restore)})


if __name__ == '__main__': main()
