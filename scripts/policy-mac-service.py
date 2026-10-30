#!/usr/bin/env python3
"""Foreground launchd entry. Secrets stay in existing private environment files."""
import pathlib, os, re, json
ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN = pathlib.Path.home() / 'Documents/policy-downloads/mac-20260930'
if (RUN / 'STOP').exists():
    print('Collector stopped by STOP file; not restarted.')
    raise SystemExit(0)
env = os.environ.copy()
env['PATH'] = '/usr/local/bin:/usr/bin:/bin:/opt/miniconda3/bin'
for file in [pathlib.Path.home() / 'Documents/global-trade-dashboard-local/.env.local', pathlib.Path.home() / 'Documents/New for anti/google_studio_key.env']:
    if not file.exists():
        if file.name == '.env.local':
            raise SystemExit('Required private environment file missing')
        continue
    for line in file.read_text().splitlines():
        match = re.match(r'^\s*(?:export\s+)?([\w]+)\s*=\s*(.*)$', line)
        if match:
            env.setdefault(match[1], match[2].strip().strip('\"\''))
if not env.get('AI_STUDIO_API_KEY'):
    env['AI_STUDIO_API_KEY'] = env.get('GEMINI_API_KEY') or env.get('GOOGLE_API_KEY', '')
try:
    state = json.loads((RUN / 'status.json').read_text())
    if state.get('next_cycle_at'):
        env['POLICY_RESUME_AT'] = state['next_cycle_at']
except FileNotFoundError:
    pass
os.chdir(ROOT)
# launchd itself need not open a log or chdir in Documents. The authorized
# collector opens its own private log after startup.
fd = os.open(RUN / 'runner.log', os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
os.dup2(fd, 1)
os.dup2(fd, 2)
os.close(fd)
os.execve('/usr/bin/caffeinate', ['caffeinate', '-i', '/usr/local/bin/node', 'scripts/run-policy-mac-temporary.js'], env)
