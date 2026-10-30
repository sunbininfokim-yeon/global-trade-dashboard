"""Offline packet replay keeps earlier publisher rechecks (CA·AL·OH·MA 2026-10-23/24)."""
import unittest
from election_watch.poll_primary_supplements import keep_unreachable_primary_receipts

DOCS = ['https://example.org/a.pdf', 'https://example.org/b.pdf']


def receipt(status, doc_status, reviewed='2026-10-21', urls=DOCS):
    docs = [{'url': u, 'status': doc_status, **({'sha256': 'x'} if doc_status != 'unavailable' else {'error_type': 'URLError'})} for u in urls]
    return {'id': 'p1', 'state': 'CA', 'status': status, 'original_reviewed_on': reviewed, 'checked_at': 'new', 'documents': docs}


OLD = {'receipt': {'primary_supplement_receipts': [receipt('primary_documents_rechecked', 'unchanged') | {'checked_at': 'old'}]},
       'primary_records': [{'id': 'p1', 'primary_source_capture': {'status': 'primary_documents_rechecked'}}]}


class KeepUnreachablePrimaryReceiptsTests(unittest.TestCase):
    def run_case(self, new):
        record = {'id': 'p1', 'primary_source_capture': {'status': new['status']}}
        return keep_unreachable_primary_receipts(OLD, [new], [record, {'id': 'other'}])

    def test_unreachable_documents_keep_the_previous_recheck(self):
        receipts, records, kept = self.run_case(receipt('carried_forward_reference_only', 'unavailable'))
        self.assertEqual(kept, {'p1'})
        self.assertEqual(receipts[0]['status'], 'primary_documents_rechecked')
        self.assertEqual(receipts[0]['checked_at'], 'old')
        self.assertEqual(records[0]['primary_source_capture']['status'], 'primary_documents_rechecked')
        self.assertEqual(records[1], {'id': 'other'})

    def test_changed_document_new_review_or_new_document_set_is_not_masked(self):
        for new in (receipt('carried_forward_reference_only', 'changed_review_required'),
                    receipt('carried_forward_reference_only', 'unavailable', reviewed='2026-10-24'),
                    receipt('carried_forward_reference_only', 'unavailable', urls=DOCS[:1])):
            receipts, records, kept = self.run_case(new)
            self.assertFalse(kept)
            self.assertEqual(receipts[0]['status'], 'carried_forward_reference_only')

    def test_no_previous_packet_or_previous_carry_forward_changes_nothing(self):
        new = receipt('carried_forward_reference_only', 'unavailable')
        self.assertFalse(keep_unreachable_primary_receipts(None, [new], [])[2])
        carried = {'receipt': {'primary_supplement_receipts': [receipt('carried_forward_reference_only', 'unavailable')]},
                   'primary_records': OLD['primary_records']}
        self.assertFalse(keep_unreachable_primary_receipts(carried, [new], [])[2])


def html(status, failures, sha='c1'):
    return {'id': 'h1', 'kind': 'html_table', 'state': 'NE', 'contract_id': 'k', 'contract_sha256': sha, 'failures': failures,
            'record': {'id': 'h1', 'primary_source_capture': {'status': status}}}


HEALTH_OK = {'kind': 'html_table_health', 'contract_id': 'k', 'status': 'ok_reference_only', 'failures': []}
NET = [{'error_type': 'URLError', 'reason': 'offline'}]


class KeepUnreachableHtmlTableTests(unittest.TestCase):
    def setUp(self):
        self.old = {'receipt': {'primary_supplement_receipts': [html('primary_documents_rechecked', []), HEALTH_OK]},
                    'primary_records': [{'id': 'p0'}, {'id': 'h1', 'primary_source_capture': {'status': 'primary_documents_rechecked'}}, {'id': 'p2'}]}

    def test_unreachable_table_keeps_row_health_and_record_order(self):
        new = [html('carried_forward_reference_only', NET), {**HEALTH_OK, 'status': 'partial_last_good_preserved', 'failures': NET}]
        receipts, records, kept = keep_unreachable_primary_receipts(self.old, new, [{'id': 'p0'}, {'id': 'p2'}])
        self.assertEqual(kept, {'h1'})
        self.assertEqual(receipts, self.old['receipt']['primary_supplement_receipts'])
        self.assertEqual([r['id'] for r in records], ['p0', 'h1', 'p2'])

    def test_changed_table_row_or_contract_is_not_masked(self):
        for new in ([html('carried_forward_reference_only', [{'reason': 'same_wave_changed_review_required', 'id': 'h1'}])],
                    [html('carried_forward_reference_only', NET, sha='c2')]):
            receipts, _, kept = keep_unreachable_primary_receipts(self.old, new, [])
            self.assertFalse(kept)
            self.assertEqual(receipts[0]['record']['primary_source_capture']['status'], 'carried_forward_reference_only')


if __name__ == '__main__':
    unittest.main()
