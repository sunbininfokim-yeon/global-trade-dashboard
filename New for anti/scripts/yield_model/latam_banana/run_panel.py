"""One-shot: optional POWER risk collect + reference JSON."""

from __future__ import annotations

import sys

from . import build_reference, collect_risk


def main() -> int:
    offline = "--offline" in sys.argv
    if not offline:
        print("[run_panel] collecting POWER risk…", flush=True)
        collect_risk.main()
    else:
        print("[run_panel] --offline: skip POWER", flush=True)
    return build_reference.main()


if __name__ == "__main__":
    raise SystemExit(main())
