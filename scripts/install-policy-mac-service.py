#!/usr/bin/env python3
"""Register the existing Mac collector; refuse to replace an active task."""
import json, pathlib, plistlib, subprocess, os, time

root = pathlib.Path(__file__).resolve().parents[1]
run = pathlib.Path.home() / 'Documents/policy-downloads/mac-20260930'
if (run / 'STOP').exists():
    raise SystemExit('STOP exists; service was not installed or restarted')
state = json.loads((run / 'status.json').read_text())
if state.get('active_task') or state.get('status') == 'running':
    raise SystemExit('Wait for a collection boundary before installing')
label = 'com.chokemonitor.policy-mac'
file = pathlib.Path.home() / 'Library/LaunchAgents' / (label + '.plist')
domain = f'gui/{os.getuid()}'
if file.exists():
    subprocess.run(['/bin/launchctl', 'bootout', domain, str(file)], check=True)
    for _ in range(30):
        try:
            os.kill(state['pid'], 0)
        except ProcessLookupError:
            break
        time.sleep(1)
    else:
        raise SystemExit('Prior collector still alive; replacement was not started')
else:
    # A foreground collector must be stopped normally by the operator first.
    try:
        os.kill(state['pid'], 0)
    except ProcessLookupError:
        pass
    else:
        raise SystemExit('Existing foreground collector is alive; stop it at its wait boundary first')
file.parent.mkdir(parents=True, exist_ok=True)
file.write_bytes(plistlib.dumps({
    'Label': label,
    'ProgramArguments': ['/opt/miniconda3/bin/python3', str(root / 'scripts/policy-mac-service.py')],
    'WorkingDirectory': str(pathlib.Path.home()),
    'RunAtLoad': True,
    'KeepAlive': {'SuccessfulExit': False},
    'ThrottleInterval': 60,
    'StandardOutPath': '/tmp/chokemonitor-policy-launch.log',
    'StandardErrorPath': '/tmp/chokemonitor-policy-launch.log',
}))
file.chmod(0o600)
subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(file)], check=True)
print(f'Installed {label}; next cycle is read from the existing private status file.')
