"""Call Claude's unchanged FuelEU implementation in a separate interpreter.

Both tool directories contain engine.py. Process isolation avoids rebinding
the shipping-carbon server's engine module while reusing the FuelEU engine.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def call_fueleu(payload, timeout=30):
    completed = subprocess.run([sys.executable, str(ROOT / "fueleu_worker.py")],
        input=json.dumps(payload, allow_nan=False), text=True, capture_output=True,
        cwd=ROOT, timeout=timeout, check=False)
    if completed.returncode:
        raise ValueError("FuelEU adapter failed: " + completed.stderr[-1000:])
    result = json.loads(completed.stdout)
    if "error" in result:
        raise ValueError(result["error"])
    return result
