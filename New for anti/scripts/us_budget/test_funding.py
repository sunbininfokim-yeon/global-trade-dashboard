import copy
import hashlib
import json
import unittest

import funding as f


class FundingTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(f.REVIEW.read_text())
        m = self.profile['measures'][0]
        references = ' '.join(f"({a['item']}) The funding area " +
                              (f"division {a['base_division']} of " if a['base_division'] else '') +
                              f"Public Law {a['base_law']}." for a in m['areas'])
        self.raw = ("<pre>[119th Congress Public Law 103] Public Law 119-103 [H.R. 6500] " + m['title'] +
                    " Be it enacted. Sec. 101. " + references + " Sec. 102. Other rules. " +
                    "Sec. 106. whichever of the following first occurs: December 11, 2026. Sec. 107. End. Approved September 2, 2026.</pre>").encode()
        m['reviewed_raw_sha256'] = hashlib.sha256(self.raw).hexdigest()

    def test_exact_law_bill_deadline_and_all_references_are_verified(self):
        result = f.verify_measure(self.profile['measures'][0], self.raw, '2026-11-01T00:00:00+00:00')
        self.assertEqual(result['verification_status'], 'verified')
        self.assertEqual(len(result['areas']), 12)
        self.assertEqual(result['current_effect_status'], 'not_determined')

    def test_wrong_identity_deadline_or_base_reference_is_rejected(self):
        for old, new in [(b'H.R. 6500', b'H.R. 6501'), (b'December 11', b'December 12'),
                         (b'Public Law 119-86', b'Public Law 119-85'), (b'whichever of the following first occurs', b'until'),
                         (b'Approved September 2', b'Approved September 3')]:
            with self.assertRaises(ValueError):
                f.verify_measure(self.profile['measures'][0], self.raw.replace(old, new), '2026-11-01')

    def test_source_changes_require_review_even_if_the_key_clauses_match(self):
        result = f.verify_measure(self.profile['measures'][0], self.raw+b' ', '2026-11-01')
        self.assertEqual(result['verification_status'], 'needs_review')

    def test_bill_number_without_congress_is_not_an_identity(self):
        for value in ['hr6500','hr-6500','119-hr-0','120-house-6500']:
            with self.assertRaises(ValueError): f.bill_id(value)
        self.assertEqual(f.bill_id('120-s-5'), '120-s-5')

    def test_discovery_is_a_review_queue_in_any_congress(self):
        raw=b'<table><tr><td>120-5</td><td>S. 5</td><td>Continuing Appropriations Act</td><td>Jan 2, 2027</td></tr></table>'
        rows = f.discovery(raw, set())
        self.assertEqual(rows[0]['status'],'needs_review')
        self.assertEqual(rows[0]['public_law_number'],'120-5')
        self.assertEqual(f.discovery(raw, {'120-5'}), [])
        with self.assertRaises(ValueError): f.discovery(b'<p>blocked</p>', set())

    def test_failed_discovery_preserves_candidates_and_exposes_unavailable_state(self):
        def get(url):
            if url==self.profile['measures'][0]['govinfo_url']: return self.raw
            raise OSError('upstream unavailable')
        previous={'discovery':{'candidates':[{'public_law_number':'119-200','status':'needs_review'}]}}
        result=f.collect(get,previous,now='2026-11-01T00:00:00+00:00',profile=self.profile)
        self.assertEqual(result['discovery']['status'],'source_unavailable')
        self.assertEqual(len(result['discovery']['candidates']),1)
        self.assertEqual(result['cost_estimates'][0]['direct_fetch_status'],'http_403')

    def test_cbo_cumulative_effect_and_version_must_reconcile(self):
        source=self.profile['cost_estimates'][0]
        self.assertEqual(f.validate_cost(source),source)
        for mutate in [lambda e:e.update(version_match='enacted'),
                       lambda e:e['budget_effects']['deficit_million'].__setitem__(1,0),
                       lambda e:e['budget_effects']['cumulative'][0].update(outlays_million=0)]:
            bad=copy.deepcopy(source);mutate(bad)
            with self.assertRaises(ValueError):f.validate_cost(bad)

    def test_current_index_does_not_drop_older_unreviewed_candidates(self):
        def get(url):
            if url==f.INDEX:return b'<table><tr><td>120-5</td><td>S. 5</td><td>Continuing Appropriations Act</td><td>Jan 2, 2027</td></tr></table>'
            return self.raw
        previous={'discovery':{'candidates':[{'public_law_number':'119-200','status':'needs_review'},
                                            {'public_law_number':'119-103','status':'needs_review'}]}}
        result=f.collect(get,previous,now='2026-11-01T00:00:00+00:00',profile=self.profile)
        self.assertEqual({r['public_law_number'] for r in result['discovery']['candidates']},{'119-200','120-5'})

    def test_new_pdf_is_not_promoted_and_its_receipt_survives_retry_cooldown(self):
        calls=[]
        def get(url):
            calls.append(url)
            if url==self.profile['cost_estimates'][0]['source_url']:return b'%PDF-synthetic test source'
            if url==f.INDEX:raise OSError('unavailable')
            return self.raw
        first=f.collect(get,now='2026-11-08T00:00:00+00:00',profile=self.profile)
        e=first['cost_estimates'][0]
        self.assertEqual(e['direct_fetch_status'],'downloaded_requires_review')
        self.assertEqual(e['annualized'],self.profile['cost_estimates'][0]['annualized'])
        calls.clear();second=f.collect(get,first,now='2026-11-09T00:00:00+00:00',profile=self.profile)
        self.assertNotIn(e['source_url'],calls)
        self.assertEqual(second['cost_estimates'][0]['latest_download_sha256'],e['latest_download_sha256'])


if __name__=='__main__':unittest.main()
