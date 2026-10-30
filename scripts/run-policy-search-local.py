#!/usr/bin/env python3
"""Load existing private keys without displaying them; run the Mac indexer."""
import os, pathlib, re, subprocess, sys
root = pathlib.Path(__file__).resolve().parents[1]
env = os.environ.copy()
for file in [pathlib.Path.home() / 'Documents/global-trade-dashboard-local/.env.local',
             pathlib.Path.home() / 'Documents/New for anti/google_studio_key.env']:
    if not file.exists():
        raise SystemExit(f'Required local environment file is missing: {file.name}')
    for line in file.read_text().splitlines():
        match = re.match(r'^\s*(?:export\s+)?([\w]+)\s*=\s*(.*)$', line)
        if match:
            env.setdefault(match[1], match[2].strip().strip('\"\''))
env['GEMINI_API_KEY'] = env.get('GEMINI_API_KEY') or env.get('AI_STUDIO_API_KEY') or env.get('GOOGLE_API_KEY', '')
env.setdefault('POLICY_SEARCH_CACHE_DIR', str(pathlib.Path.home() / 'Documents/policy-downloads/search-corpus-20261005'))
env.setdefault('EO_OFFICIAL_TEXT_CACHE_DIR', str(pathlib.Path.home() / 'Documents/policy-downloads/eo-official-text'))
env.setdefault('POLICY_COLLECTOR_STOP_FILE', str(pathlib.Path.home() / 'Documents/policy-downloads/mac-20260930/STOP'))
raise SystemExit(subprocess.call(['/usr/local/bin/node', str(root / 'scripts/sync-policy-search.js'), *sys.argv[1:]], cwd=root, env=env))
