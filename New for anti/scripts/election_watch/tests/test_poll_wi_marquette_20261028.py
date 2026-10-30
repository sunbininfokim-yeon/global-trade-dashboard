"""WI: Marquette's final 2026 poll (Oct 14-22) is absent from VoteHub and enters as a reviewed primary record."""
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.poll_quality import answer_correction_fingerprint
from election_watch.state_inputs import validate_packet

ROOT = Path(__file__).resolve().parents[1]
ID = 'primary-marquette-wi-governor-lv-20261028'
PDF = 'https://law.marquette.edu/assets/community/poll/MLSP92/MLSP92PressRelease.pdf'


class WisconsinMarquetteFinalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = read(ROOT/'config/state_evidence/2026/WI.json')
        cls.ops = {(op['file'], op['path'][-1]): op for op in cls.packet['config_operations']}

    def test_packet_is_valid_and_owns_only_wisconsin(self):
        names = {s: v['name'] for s, v in read(ROOT/'config/usa_polls/targets_2026.json')['states'].items()}
        validate_packet(self.packet, names)

    def test_primary_record_matches_the_release_pdf(self):
        entry = self.ops[('usa_polls/primary_supplements_2026.json', 'records')]['value']
        rec = entry['record']
        self.assertEqual(rec['id'], ID)
        self.assertEqual((rec['population'], rec['sample_size'], rec['start_date'], rec['end_date']), ('lv', 668, '2026-10-14', '2026-10-22'))
        self.assertEqual({a['choice']: a['pct'] for a in rec['answers']}, {'David Crowley': 51.0, 'Tom Tiffany': 44.0})
        self.assertEqual(entry['record_sha256'], answer_correction_fingerprint(rec))
        self.assertEqual(entry['documents'][0]['url'], PDF)
        review = self.ops[('usa_polls/quality_reviews_2026.json', ID)]['value']
        self.assertTrue(review['admission']['signal_eligible'])
        self.assertEqual(review['disclosure_review']['likely_voter_n'], 668)

    def test_capture_rechecked_the_archived_release(self):
        receipts = {r['id']: r for r in self.packet['capture']['receipt']['primary_supplement_receipts']}
        self.assertEqual(receipts[ID]['status'], 'primary_documents_rechecked')
        self.assertEqual(receipts[ID]['documents'][0]['status'], 'unchanged')


if __name__ == '__main__':
    unittest.main()
