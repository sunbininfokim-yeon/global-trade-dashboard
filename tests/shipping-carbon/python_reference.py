"""Run the PR #789 Python engine on each case from stdin and print JSON results.

Used by engine.test.mjs so the browser port is checked against the reference,
not against numbers copied into the test.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "shipping_carbon"))
from engine import calculate, defaults, json_value  # noqa: E402

snapshot = json.loads((Path(__file__).resolve().parents[2] / "tools/shipping_carbon/synthetic_snapshot.json").read_text())
out = []
for changes in json.load(sys.stdin):
    try:
        out.append({"ok": json_value(calculate({**defaults(snapshot), **changes}, snapshot))})
    except ValueError as exc:
        out.append({"error": str(exc)})
print(json.dumps(out, ensure_ascii=False))
