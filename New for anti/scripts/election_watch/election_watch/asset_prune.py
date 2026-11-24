"""Retire superseded content-addressed election assets.

Hashed assets (``<prefix>-<16 hex>.json``) are immutable: a generator writes a
new one and the index commit makes it live. Nothing ever removed the old ones,
so the static bundle grew past Cloudflare's 20,000-file limit (2026-11-24).

A hashed file is kept when either is true:

* any public JSON outside the hashed assets reaches it (indexes, but also
  ``usa_election_live_polls_v1.json``, poll release reviews, ...), following
  references through other assets;
* the previous generation of the index reached it. A browser or CDN may still
  hold the last index for a short while, so one generation is retained.

Fixed-name files inside the folders (``governor_context_inputs_v1.json`` and
friends) are inputs read by scripts and are never removed.
"""
from collections import defaultdict
import json
from pathlib import Path
import re

FOLDERS = ('usa_election_finance', 'usa_superpac', 'usa_election_state_evidence')
HASHED = re.compile(r'^(?P<prefix>.+)-[0-9a-f]{16}\.json$')
_MARKERS = tuple(f + '/' for f in FOLDERS)


def _names(obj):
    names, stack = set(), [obj]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, str) and item.endswith('.json'):
            names.add(item.rsplit('/', 1)[-1])
    return names


def _assets(public):
    by_name = defaultdict(list)
    for folder in FOLDERS:
        base = public / folder
        if base.is_dir():
            for path in base.rglob('*.json'):
                by_name[path.name].append(path.relative_to(public).as_posix())
    return by_name


def reachable(public, extra_roots=()):
    """Paths (relative to ``public``) of folder files some root reaches."""
    public = Path(public)
    by_name = _assets(public)
    todo = []

    def visit(obj):
        for name in _names(obj):
            todo.extend(by_name.get(name, ()))

    for path in public.rglob('*.json'):
        rel = path.relative_to(public).as_posix()
        if rel.startswith(_MARKERS) and HASHED.match(path.name):
            continue  # an asset is only ever reached, never a root by itself
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        if not any(marker in text for marker in _MARKERS):
            continue
        # A root we cannot parse may still point at assets: refuse to guess.
        visit(json.loads(text))
    for obj in extra_roots:
        visit(obj)
    seen = set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        visit(json.loads((public / rel).read_text(encoding='utf-8')))
    return seen


def stale(public, folder, previous_roots=(), prefixes=None):
    """Hashed files in ``folder`` neither the current nor previous roots reach."""
    if folder not in FOLDERS:
        raise ValueError(f'not a pruned asset folder: {folder}')
    public = Path(public)
    keep = reachable(public, previous_roots)
    out = []
    base = public / folder
    for path in sorted(base.rglob('*.json')) if base.is_dir() else ():
        match = HASHED.match(path.name)
        if not match or (prefixes is not None and match['prefix'] not in prefixes):
            continue
        rel = path.relative_to(public).as_posix()
        if rel not in keep:
            out.append(rel)
    return out


def prune(public, folder, previous_roots=(), prefixes=None):
    """Delete stale hashed files; returns the removed relative paths."""
    removed = stale(public, folder, previous_roots, prefixes)
    for rel in removed:
        (Path(public) / rel).unlink()
    return removed


def unretained(public):
    """Shards holding more than one unreachable generation (guard check)."""
    public = Path(public)
    keep = reachable(public)
    counts = defaultdict(list)
    for folder in FOLDERS:
        base = public / folder
        for path in base.rglob('*.json') if base.is_dir() else ():
            match = HASHED.match(path.name)
            rel = path.relative_to(public).as_posix()
            if match and rel not in keep:
                counts[f'{path.parent.relative_to(public).as_posix()}/{match["prefix"]}'].append(rel)
    return {shard: sorted(files) for shard, files in sorted(counts.items()) if len(files) > 1}
