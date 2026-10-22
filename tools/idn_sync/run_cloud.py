"""Run the pinned IDN collector; preserve state even on a recoverable failure."""
import argparse
import json
import os
from pathlib import Path
import sys
from cloud_state import Storage

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--collector',required=True,type=Path);parser.add_argument('--state-dir',required=True,type=Path)
    args=parser.parse_args()
    sys.path.insert(0,str(args.collector.resolve()/'scripts/indonesia_policy'))
    from scheduled_sync import run
    from sync_reviewed import Gateway
    rpc=Gateway();remote=Storage(rpc.url,rpc.key)
    # A missing snapshot is an error, never a silent restart from zero.
    remote.restore(args.state_dir)
    if (args.state_dir/'STOP').exists(): raise SystemExit('Remote STOP preserved; collection not started')
    try:
        result=run(args.state_dir,rpc,refresh_limit=20,discovery_limit=5)
        print(json.dumps(result),flush=True)
    finally:
        size=remote.save(args.state_dir)
        print(json.dumps({'checkpoint_saved':True,'bytes':size}),flush=True)

if __name__=='__main__': main()
