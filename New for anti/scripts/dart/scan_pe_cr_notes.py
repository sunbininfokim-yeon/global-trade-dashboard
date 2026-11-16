"""One-document pilot: public filing rows -> review queue, never engine facts."""
import argparse
import json
import os
from pathlib import Path

from dart_kfa.gemini_note_candidates import MAX_BYTES, candidate_report, scan_with_gemini


def _read_json(path):
    with path.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input_too_large")
    return json.loads(raw)


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("packet", type=Path, help="verified public DART/SEC table rows")
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replay", type=Path, help="offline model-selection fixture; no request")
    mode.add_argument("--send-public-rows", action="store_true", help="one Google request; confirms labels are from public filings")
    cli.add_argument("--model", help="generation model enabled for this key (or GEMINI_NOTES_MODEL)")
    args = cli.parse_args(argv)
    try:
        packet = _read_json(args.packet)
        if args.replay:
            report = candidate_report(packet, _read_json(args.replay))
        else:
            report = scan_with_gemini(packet, model=args.model or os.environ.get("GEMINI_NOTES_MODEL"),
                                      api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_STUDIO_API_KEY"))
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (json.JSONDecodeError, UnicodeError):
        cli.exit(1, "error: invalid_json\n")
    except OSError:
        cli.exit(1, "error: unable_to_read_input\n")
    except ValueError as exc:
        cli.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
