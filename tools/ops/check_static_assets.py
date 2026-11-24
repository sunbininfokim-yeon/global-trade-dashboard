#!/usr/bin/env python3
"""Keep the Worker's static bundle under Cloudflare's per-version file cap.

Workers Free accepts at most 20,000 static files per version. On 2026-11-24
main held 20,119 and every deploy failed: generators wrote a new hashed file
per refresh and never retired the old one.

Checks:
  * deploy-target file count (``.assetsignore`` applied): warn above 18,000,
    fail above 20,000;
  * hashed election assets: per shard at most one unreachable (previous)
    generation -- see scripts/election_watch/election_watch/asset_prune.py.

Usage: python3 tools/ops/check_static_assets.py [--assets "New for anti"]
"""
import argparse
import fnmatch
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIMIT, WARN = 20_000, 18_000


def ignore_patterns(assets):
    path = assets / '.assetsignore'
    if not path.exists():
        return []
    lines = (line.strip() for line in path.read_text(encoding='utf-8').splitlines())
    return [line for line in lines if line and not line.startswith('#')]


def ignored(rel, patterns):
    """gitignore-style subset used by .assetsignore (no negation)."""
    parts = rel.split('/')
    for raw in patterns:
        pat = raw.rstrip('/')
        anchored = '/' in pat.lstrip('/')
        pat = pat.lstrip('/')
        if pat.endswith('/**'):
            pat = pat[:-3]
        if anchored:
            # The pattern names a file or a directory relative to the root.
            if any(fnmatch.fnmatchcase('/'.join(parts[:i]), pat) for i in range(1, len(parts) + 1)):
                return True
        elif any(fnmatch.fnmatchcase(part, pat) for part in parts):
            return True
    return False


def deploy_files(assets):
    patterns = ignore_patterns(assets)
    out = []
    for path in assets.rglob('*'):
        if path.is_file():
            rel = path.relative_to(assets).as_posix()
            if not ignored(rel, patterns):
                out.append(rel)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=pathlib.Path, default=ROOT / 'New for anti')
    args = parser.parse_args()
    count = len(deploy_files(args.assets))
    failed = False
    print(f'deploy static files: {count} (warn > {WARN}, limit {LIMIT})')
    if count > LIMIT:
        print(f'::error::{count} static files exceed the Cloudflare limit of {LIMIT}')
        failed = True
    elif count > WARN:
        print(f'::warning::{count} static files; Cloudflare limit is {LIMIT}')

    sys.path.insert(0, str(args.assets / 'scripts' / 'election_watch'))
    from election_watch.asset_prune import unretained
    extra = unretained(args.assets / 'public' / 'data')
    for shard, files in extra.items():
        print(f'::error::{shard}: {len(files)} unreachable generations (max 1), e.g. {files[0]}')
    failed = failed or bool(extra)
    print(f'election asset shards over retention: {len(extra)}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
