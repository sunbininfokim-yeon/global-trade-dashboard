from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import refresh_budget as r
import publish_budget as p


def dataset(period='2026-09-30'):
    value = dict(schema_version=1, annual=dict(proposal_fy=2027, publication='2026/04'),
                 live=dict(mts_record_date=period, months=[dict(month='2026-09', receipts=1, outlays=2, deficit=1, vintage=period)]))
    value['dataset_id'] = hashlib.sha256(r.encode(value)).hexdigest()
    return value


class PipelineTests(unittest.TestCase):
    def test_failure_keeps_monetary_data_and_success_time(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before = r.encode(dataset())
            r.atomic(root / r.BUNDLE, before)
            r.atomic(root / r.STATUS, r.encode(dict(state='ok', last_success_at='2026-11-01T00:00:00+00:00')))
            with patch.object(r, 'assemble', side_effect=ValueError('invalid source')), redirect_stderr(StringIO()):
                self.assertEqual(r.run(root, root, now='2026-11-02T00:00:00+00:00'), 1)
            self.assertEqual((root / r.BUNDLE).read_bytes(), before)
            status = r.read(root / r.STATUS)
            self.assertEqual(status['state'], 'failed')
            self.assertEqual(status['last_success_at'], '2026-11-01T00:00:00+00:00')

    def test_same_vintage_revisions_are_audited_and_not_discarded(self):
        previous = dataset()
        current = copy.deepcopy(previous)
        current['live']['months'][0]['outlays'] = 4
        changes = r.revisions(previous, current)
        self.assertEqual(changes[0]['before'], 2)
        self.assertEqual(changes[0]['after'], 4)
        self.assertEqual(changes[0]['old_vintage'], changes[0]['new_vintage'])

    def test_publisher_rejects_corruption_before_touching_published_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); staged = root / 'staged'; output = root / 'out'
            value = dataset()
            r.atomic(staged / r.BUNDLE, r.encode(value))
            r.atomic(staged / r.STATUS, r.encode(dict(schema_version=1, state='ok', dataset_id=value['dataset_id'], last_checked_at='2026-11-01')))
            value['annual']['proposal_fy'] = 2028
            r.atomic(staged / r.BUNDLE, r.encode(value))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'): p.publish(staged, output, 'success')
            self.assertFalse((output / r.BUNDLE).exists())

    def test_failure_publication_cannot_replace_the_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); staged = root / 'staged'; output = root / 'out'
            before = r.encode(dataset())
            r.atomic(output / r.BUNDLE, before)
            r.atomic(output / r.STATUS, r.encode(dict(last_success_at='2026-10-31')))
            r.atomic(staged / r.STATUS, r.encode(dict(schema_version=1, state='failed', last_checked_at='2026-11-01')))
            r.atomic(staged / r.BUNDLE, b'{}')  # An accidental staged data file is ignored.
            p.publish(staged, output, 'failure')
            self.assertEqual((output / r.BUNDLE).read_bytes(), before)
            self.assertEqual(r.read(output / r.STATUS)['last_success_at'], '2026-10-31')

    def test_older_receipt_cannot_replace_a_newer_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); staged = root / 'staged'; output = root / 'out'
            r.atomic(output / r.STATUS, r.encode(dict(last_checked_at='2026-11-02')))
            r.atomic(staged / r.STATUS, r.encode(dict(schema_version=1, state='failed', last_checked_at='2026-11-01')))
            with self.assertRaisesRegex(ValueError, 'older'): p.publish(staged, output, 'failure')


if __name__ == '__main__': unittest.main()
