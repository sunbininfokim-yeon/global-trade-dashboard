import copy
import json
import unittest
import build_funding_context as context


class ContextTests(unittest.TestCase):
    def setUp(self):self.profile=json.loads(context.PROFILE.read_text())

    def test_published_context_is_generated_from_reviewed_profile(self):
        self.assertEqual(context.build(),context.OUTPUT.read_bytes())

    def test_future_or_unattributed_claims_are_rejected(self):
        for change in [lambda d:d.update(reviewed_on='2026-11-01'),
                       lambda d:d['issues'][0].update(sources=['not-a-source']),
                       lambda d:d['procedure'].update(house_passed=13),
                       lambda d:d['issues'][0].update(as_of='2026-10-20')]:
            p=copy.deepcopy(self.profile);change(p)
            with self.assertRaises(ValueError):context.validate(p)

    def test_untrusted_or_executable_sources_are_rejected(self):
        for url in ['javascript:alert(1)','https://example.com/','http://www.cbo.gov/']:
            p=copy.deepcopy(self.profile);p['sources'][0]['url']=url
            with self.assertRaises(ValueError):context.validate(p)

    def test_unknown_issue_state_is_rejected(self):
        p=copy.deepcopy(self.profile);p['issues'][-1]['state']='current_fact'
        with self.assertRaises(ValueError):context.validate(p)


if __name__=='__main__':unittest.main()
