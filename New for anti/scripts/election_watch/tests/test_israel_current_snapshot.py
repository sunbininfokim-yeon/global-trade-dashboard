"""Current snapshot integration; derive the evidence clock from review receipts."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from election_watch.israel_analysis import build, health, read_inputs

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'config/israel/2026'
PUBLIC = ROOT.parents[1] / 'public/data'


class IsraelCurrentSnapshotTests(unittest.TestCase):
    def test_current_publication_replays_from_reviewed_inputs(self):
        inputs = read_inputs(INPUT)
        saved = json.loads((PUBLIC / 'israel_election_analysis_v1.json').read_text())
        as_of = inputs['review_receipts.json']['evidence_as_of']
        board = build(inputs, as_of, saved['built_at'])
        self.assertEqual(board, saved)
        self.assertEqual(health(board), json.loads((PUBLIC / 'israel_election_analysis_status_v1.json').read_text()))

    def test_documented_cli_default_matches_current_receipt(self):
        as_of = read_inputs(INPUT)['review_receipts.json']['evidence_as_of']
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'israel_election_analysis_v1.json'
            result = subprocess.run([sys.executable, str(ROOT / 'build_israel_analysis.py'),
                                     '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                             'Update the CLI --as-of default together with review_receipts.evidence_as_of.\n' + result.stderr)
            self.assertEqual(json.loads(output.read_text())['evidence_as_of'], as_of)
