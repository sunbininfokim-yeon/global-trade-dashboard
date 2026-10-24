import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from recover_official import recover, urls


def entry(name='idn-test'):
    return dict(document_id=name, url='https://publisher.go.id/law',
                official_alternatives=['https://archive.go.id/law.pdf'], identity_phrases=['NOMOR 1'])


def complete(e):
    return dict(document_id=e['document_id'], country_code='IDN', legal_status='unverified',
                source_url=e['url'], content_kind='official_text', body_status='extracted', text_truncated=False)


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(str(status), response=response)


class OfficialRecoveryTests(unittest.TestCase):
    def run_pack(self, entries, collector):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'new'
            result = recover(entries, path, collector=collector, pause=lambda _: None)
            self.assertEqual(json.loads((path / 'collection.json').read_text()), result)
            return result

    def test_verified_alternative_keeps_real_source_and_original_failure(self):
        calls = []
        def collector(e, *_):
            calls.append(e['url'])
            if len(calls) == 1:
                raise http_error(403)
            return complete(e)
        result = self.run_pack([entry()], collector)
        self.assertEqual(result['documents'][0]['source_url'], 'https://archive.go.id/law.pdf')
        self.assertEqual(result['source_attempts'][0]['http_status'], 403)
        self.assertEqual(result['failures'], [])

    def test_block_and_maintenance_skip_other_paths_and_later_documents_on_host(self):
        for status in (403, 429, 503):
            first = entry()
            first['official_alternatives'] = ['https://publisher.go.id/other.pdf']
            second = {**entry('idn-second'), 'official_alternatives': []}
            collector = Mock(side_effect=http_error(status))
            result = self.run_pack([first, second], collector)
            collector.assert_called_once()
            self.assertEqual(len(result['failures']), 2)
            self.assertEqual([a['outcome'] for a in result['source_attempts']], ['failed', 'deferred', 'deferred'])

    def test_metadata_truncated_and_ocr_outputs_are_never_recovered_originals(self):
        for extra in ({'content_kind': 'official_metadata'}, {'text_truncated': True}, {'body_status': 'local_ocr_selected_pages_reviewed'}):
            result = self.run_pack([{**entry(), 'official_alternatives': []}], lambda e, *_: {**complete(e), **extra})
            self.assertEqual(result['documents'], [])
            self.assertEqual(len(result['failures']), 1)

    def test_identity_and_draft_failures_are_held_without_a_fake_document(self):
        for error in ('document_identity_not_verified', 'draft_or_unclassified_document'):
            result = self.run_pack([entry()], Mock(side_effect=ValueError(error)))
            self.assertEqual(result['documents'], [])
            self.assertTrue(all(a['reason'] == error for a in result['source_attempts']))

    def test_malformed_pack_is_rejected_before_any_request(self):
        invalid = [
            {**entry(), 'official_alternatives': ['https://private.example/doc']},
            {**entry(), 'official_alternatives': ['https://publisher.go.id/law']},
            {**entry(), 'official_alternatives': 'https://archive.go.id/doc'},
            {**entry(), 'official_alternatives': ['https://a.go.id/x', 'https://b.go.id/x', 'https://c.go.id/x']},
        ]
        for e in invalid:
            collector = Mock()
            with self.assertRaises(ValueError):
                self.run_pack([e], collector)
            collector.assert_not_called()

    def test_previous_evidence_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'existing'
            path.mkdir()
            (path / 'collection.json').write_text('previous')
            with self.assertRaises(ValueError):
                recover([entry()], path, collector=Mock())
            self.assertEqual((path / 'collection.json').read_text(), 'previous')

    def test_existing_host_cooldowns_are_preserved_before_any_request(self):
        with tempfile.TemporaryDirectory() as root:
            collector = Mock()
            result = recover([entry()], Path(root) / 'new', collector=collector, pause=lambda _: None,
                             initial_cooldowns={'publisher.go.id': time.time()+3600, 'archive.go.id': time.time()+3600})
            collector.assert_not_called()
            self.assertEqual(result['documents'], [])
            self.assertEqual(len(result['source_attempts']), 2)

    def test_pack_captures_corrected_title_and_related_legal_candidates(self):
        pack = json.loads(Path(__file__).with_name('sources-regional-recovery-20261024.json').read_text())
        self.assertEqual(len(pack), 5)
        for e in pack:
            urls(e)
        land = next(e for e in pack if e['document_id'] == 'idn-kalbar-perda-6-2018')
        self.assertIn('Usaha Berbasis Lahan', land['title'])
        self.assertIn('idn-kalbar-pergub-159-2021', {e['document_id'] for e in pack})
        self.assertIn('idn-kalbar-pergub-1-2024', {e['document_id'] for e in pack})


if __name__ == '__main__':
    unittest.main()
