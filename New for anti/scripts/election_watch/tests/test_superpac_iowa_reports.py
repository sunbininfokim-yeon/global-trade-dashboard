import copy
import json
from pathlib import Path
import tempfile
import unittest

from election_watch.iowa_ie_reports import collect, API
from refresh_iowa_ie_reports import refresh


class Response:
    status = 200
    def __init__(self, data): self.body = json.dumps(data).encode()
    def geturl(self): return API
    def read(self, n): return self.body[:n]
    def __enter__(self): return self
    def __exit__(self, *args): pass


class IowaReportDiscoveryTests(unittest.TestCase):
    def rows(self, n):
        return [{'id': i, 'date': '2026-10-07T00:00:00', 'filedOn': '2026-10-08T00:00:00',
                 'reportType': 'Organization Independent Expenditure', 'filingStatus': 'Certified',
                 'fileUrl': f'https://iecdbblobstorage.blob.core.windows.net/reports-prod/Report {i}.pdf',
                 'contactName': 'Personal contact excluded'} for i in range(n)]

    def opener(self, rows, total=None):
        def open_(request, timeout):
            self.assertEqual(request.full_url, API)
            self.assertEqual(request.get_method(), 'POST')
            query = json.loads(request.data)
            self.assertEqual(query['page'], 0)
            self.assertEqual(query['pageLength'], 100)
            return Response({'results': rows, 'totalCount': total if total is not None else len(rows),
                'filteredCount': total if total is not None else len(rows), 'echo': 1})
        return open_

    def test_bounded_response_remains_partial_and_has_no_candidate_money(self):
        p = collect('2026-10-09T00:00:00+00:00', self.opener(self.rows(100), 1510))
        self.assertFalse(p['cycle_discovery_complete'])
        self.assertEqual(p['cycle_reports_observed'], 100)
        self.assertFalse(p['candidate_amounts_available'])
        self.assertNotIn('contactName', p['records'][0])
        self.assertIsNone(p['records'][0]['support_cents'])
        self.assertIn('%20', p['records'][0]['file_url'])

    def test_duplicate_or_truncated_response_fails_instead_of_claiming_complete(self):
        rows = self.rows(2)
        rows[1]['id'] = rows[0]['id']
        with self.assertRaisesRegex(ValueError, 'duplicate Iowa report id'):
            collect('2026-10-09T00:00:00+00:00', self.opener(rows))
        with self.assertRaisesRegex(ValueError, 'incomplete Iowa report page'):
            collect('2026-10-09T00:00:00+00:00', self.opener(self.rows(2), 100))

    def test_unreviewed_pdf_host_and_future_dates_are_rejected(self):
        rows = self.rows(1)
        rows[0]['fileUrl'] = 'https://example.org/reports-prod/report.pdf'
        with self.assertRaisesRegex(ValueError, 'Iowa report PDF host/path changed'):
            collect('2026-10-09T00:00:00+00:00', self.opener(rows))
        rows = self.rows(1)
        rows[0]['date'] = '2026-11-03T00:00:00'
        with self.assertRaisesRegex(ValueError, 'Iowa report ordering/date changed'):
            collect('2026-10-09T00:00:00+00:00', self.opener(rows))

    def test_previous_cycle_is_not_published_as_current(self):
        rows = self.rows(2)
        rows[1]['date'] = '2025-12-31T00:00:00'
        p = collect('2026-10-09T00:00:00+00:00', self.opener(rows))
        self.assertTrue(p['cycle_discovery_complete'])
        self.assertEqual(p['cycle_reports_observed'], 1)

    def test_source_failure_preserves_last_valid_and_original_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp)
            payload = collect('2026-10-08T00:00:00+00:00', self.opener(self.rows(1)))
            self.assertEqual(refresh(public, payload['checked_at'], lambda _: payload), 0)
            path = public/'usa_governor_ie_report_indexes/2026/IA.json'
            before = path.read_bytes()
            def failure(_): raise OSError('Synthetic unavailable')
            self.assertEqual(refresh(public, '2026-10-09T00:00:00+00:00', failure), 1)
            self.assertEqual(path.read_bytes(), before)
            status = json.loads((public/'usa_governor_ie_report_index_status/2026/IA.json').read_text())
            self.assertEqual(status['status'], 'error_last_valid_preserved')
