"""Install the dedicated four-hour IDN collector; never changes the US job."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys

LABEL = 'com.chokemonitor.indonesia-policy'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--initial-cooldown-file', type=Path, required=True)
    parser.add_argument('--start', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin': raise SystemExit('macOS required')
    env = args.env_file.resolve(strict=True)
    root = args.state_dir.resolve()
    if (root/'STOP').exists(): raise SystemExit('STOP exists; scheduler not installed')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    script = Path(__file__).resolve().with_name('scheduled_sync.py')
    command = ['/usr/bin/caffeinate','-i',sys.executable,str(script),'--write',
        '--env-file',str(env),'--state-dir',str(root),'--initial-cooldown-file',
        str(args.initial_cooldown_file.resolve()),'--refresh-limit','20','--discovery-limit','5']
    target = Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    if target.exists(): raise SystemExit('Existing IDN LaunchAgent preserved; inspect before replacing')
    target.parent.mkdir(parents=True, exist_ok=True)
    # launchd cannot open a Documents working/log directory on all macOS setups.
    logs=Path.home()/'Library/Logs/chokemonitor-indonesia'
    logs.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name in ('runner.log','runner.err.log'):
        path=logs/name;path.touch(mode=0o600,exist_ok=True);path.chmod(0o600)
    data = dict(Label=LABEL,ProgramArguments=command,WorkingDirectory='/private/tmp',
        StartInterval=14400,RunAtLoad=False,StandardOutPath=str(logs/'runner.log'),
        StandardErrorPath=str(logs/'runner.err.log'),ProcessType='Background')
    target.write_bytes(plistlib.dumps(data));target.chmod(0o600)
    domain=f'gui/{os.getuid()}'
    subprocess.run(['launchctl','bootstrap',domain,str(target)],check=True)
    if args.start: subprocess.run(['launchctl','kickstart',f'{domain}/{LABEL}'],check=True)
    print(f'Installed {LABEL}: every 4 hours; state {root}')

if __name__ == '__main__': main()
