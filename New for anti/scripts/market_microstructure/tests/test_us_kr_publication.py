import copy
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

if any(importlib.util.find_spec(p) is None for p in ['numpy', 'pandas', 'scipy', 'sklearn', 'exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import us_kr_publication as publication
from option_direction_model import digest
from run_us_kr_preopen import archive_forecast, display_payload
import test_us_kr_forward as forward_tests


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        forward_tests.ForwardTests.setUpClass()

    def setUp(self):
        self.f = forward_tests.ForwardTests().forecast()
        self.f.update(record_role='first_preopen_forecast', eligible_for_primary_evaluation=True)
        for result in self.f['results'].values():
            for name, score in result['scores'].items():
                score.update(score_0_100=60, direction='UP' if name.endswith('_up') else 'MAINTAIN')
        self.payload = display_payload(self.f)

    def receipt(self, payload=None, at='2026-11-06T07:05:00+09:00'):
        response = Mock(status_code=200)
        response.json.return_value = self.payload if payload is None else payload
        return publication.observe(self.f, clock=lambda: datetime.fromisoformat(at), get=Mock(return_value=response))

    def test_matching_remote_payload_verified_and_immutable(self):
        r = self.receipt()
        self.assertTrue(r['eligible_for_publication_evaluation'])
        with tempfile.TemporaryDirectory() as root:
            path = publication.save_observation(root, self.f, r)
            original = path.read_bytes()
            self.assertEqual(publication.save_observation(root, self.f, r), path)
            self.assertEqual(original, path.read_bytes())
            directory = path.parent.parent
            evidence = publication.publication_evidence(directory, self.f, '2026-11-06T17:00:00+09:00')
            self.assertEqual(evidence['status'], 'verified')

    def test_old_target_wrong_model_changed_score_or_missing_card_rejected(self):
        for kind in ['target', 'model', 'score', 'card', 'duplicate', 'replay', 'generated', 'complement']:
            payload = copy.deepcopy(self.payload)
            if kind == 'target': payload['target_date'] = '2026-11-05'
            elif kind == 'model': payload['model_id'] = 'b'*64
            elif kind == 'score': payload['cards'][0]['scores']['opening_up']['probability'] = .7
            elif kind == 'card': payload['cards'].pop()
            elif kind == 'duplicate': payload['cards'][-1] = copy.deepcopy(payload['cards'][0])
            elif kind == 'replay': payload['status'] = 'retrospective_replay'
            elif kind == 'complement': payload['cards'][0]['scores']['closing_up']['down_probability'] = .1
            else: payload['generated_at'] = '2026-11-06T07:01:00+09:00'
            with self.subTest(kind=kind):
                self.assertFalse(self.receipt(payload)['eligible_for_publication_evaluation'])

    def test_timestamp_measured_after_fetch_and_cutoff_is_strict(self):
        after = datetime.fromisoformat('2026-11-06T08:30:01+09:00')
        state = {'now': datetime.fromisoformat('2026-11-06T08:29:59+09:00')}
        response = Mock(status_code=200); response.json.return_value = self.payload
        def fetch(*args, **kwargs):
            state['now'] = after
            return response
        receipt = publication.observe(self.f, get=fetch, clock=lambda: state['now'])
        self.assertEqual(receipt['observed_at'], publication.timestamp(after).isoformat())
        self.assertFalse(receipt['eligible_for_publication_evaluation'])
        for at in ['2026-11-06T08:30:00+09:00', '2026-11-06T06:59:59+09:00']:
            self.assertFalse(self.receipt(at=at)['eligible_for_publication_evaluation'])

    def test_refresh_metadata_and_additive_fields_do_not_change_identity(self):
        payload = copy.deepcopy(self.payload)
        payload['refresh'] = {'status': 'unavailable', 'checked_at': '2026-11-06T07:03:00+09:00'}
        payload.pop('probability_contract')
        for card in payload['cards']:
            for score in card['scores'].values():
                score.pop('up_probability', None); score.pop('down_probability', None)
        self.assertTrue(self.receipt(payload)['eligible_for_publication_evaluation'])

    def test_http_failure_not_verified_and_no_yesterday_fallback(self):
        import requests
        get = Mock(side_effect=requests.ConnectionError('provider unavailable'))
        r = publication.observe(self.f, get=get, clock=lambda: datetime.fromisoformat('2026-11-06T07:05:00+09:00'))
        self.assertEqual(r['status'], 'publication_unverified')
        self.assertNotIn('payload', r)
        self.assertFalse(r['eligible_for_publication_evaluation'])

    def test_http_200_html_fallback_is_not_a_published_forecast(self):
        response = Mock(status_code=200)
        response.json.side_effect = ValueError('HTML app fallback, not JSON')
        r = publication.observe(self.f, get=Mock(return_value=response),
                                clock=lambda: datetime.fromisoformat('2026-11-06T07:05:00+09:00'))
        self.assertEqual(r['http_status'], 200)
        self.assertEqual(r['status'], 'publication_unverified')
        self.assertFalse(r['eligible_for_publication_evaluation'])

    def test_missing_receipt_unverified_and_tampering_detected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)/self.f['target_date']/self.f['model_id'][:16]
            empty = publication.publication_evidence(directory, self.f, '2026-11-06T17:00:00+09:00')
            self.assertEqual(empty['reason'], 'no_publication_observation')
            r = self.receipt(); r['payload']['cards'][0]['scores']['closing_up']['probability'] = .7
            # Even a recomputed hash cannot turn a different prediction into the first forecast.
            r['payload_sha256'] = digest(r['payload'])
            publication.save_observation(root, self.f, r)
            bad = publication.publication_evidence(directory, self.f, '2026-11-06T17:00:00+09:00')
            self.assertEqual(bad['status'], 'unverified')
            self.assertTrue(bad['invalid_observations'])

    def test_revision_and_replay_rejected(self):
        for change in [{'record_role': 'revision'}, {'status': 'retrospective_replay'},
                       {'eligible_for_prospective_evaluation': False}]:
            with self.subTest(change=change):
                self.f.update(change)
                self.assertFalse(self.receipt()['eligible_for_publication_evaluation'])

    def test_future_observation_not_counted(self):
        with tempfile.TemporaryDirectory() as root:
            path = publication.save_observation(root, self.f, self.receipt())
            evidence = publication.publication_evidence(path.parent.parent, self.f, '2026-11-06T07:04:00+09:00')
            self.assertEqual(evidence['status'], 'unverified')

    def test_forward_scores_separate_generation_from_verified_publication(self):
        with tempfile.TemporaryDirectory() as root:
            forecast, _ = archive_forecast(self.f, root)
            self.f = forecast
            generated = forward_tests.ForwardTests().evaluate(root)
            self.assertEqual(generated['issuance']['issued_sessions'], 1)
            self.assertEqual(generated['publication_verified']['verified_sessions'], 0)
            self.assertEqual(generated['publication_verified']['all']['KOSPI']['opening_up']['primary']['n'], 0)
            publication.save_observation(root, self.f, self.receipt())
            published = forward_tests.ForwardTests().evaluate(root)
            self.assertEqual(published['publication_verified']['verified_sessions'], 1)
            self.assertEqual(published['publication_verified']['all']['KOSPI']['opening_up']['primary']['n'], 1)
            self.assertEqual(published['all'], generated['all'])
            self.assertEqual(published['issuance'], generated['issuance'])

    def test_non_https_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            publication.observe(self.f, 'http://example.test/data.json')


if __name__ == '__main__':
    unittest.main()
