from tests.poll_config_fixture import SNAPSHOT_DAY
import copy
import hashlib
import json
from pathlib import Path
import unittest
from election_watch.governor_matchups import apply_ballot_reviews, apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize, summarize
from election_watch.poll_primary_supplements import merge_primary_supplements, primary_html_fingerprint
from election_watch.poll_quality import answer_correction_fingerprint
from election_watch.superpac import SourceError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config/usa_polls'
PUBLIC = ROOT.parent.parent / 'public/data'
DAY = '2026-10-08'
read = lambda p: json.loads(p.read_text())


class CaliforniaPrimaryTests(unittest.TestCase):
    def setUp(self):
        self.gov = read(ROOT/'config/governor_matchups/2026.json')
        self.policy = apply_targets(apply_matchups(read(CONFIG/'live_2026.json'), self.gov, SNAPSHOT_DAY),
            read(CONFIG/'targets_2026.json'), read(CONFIG/'ballot_reviews_2026.json'), SNAPSHOT_DAY)
        self.policy['quality_reviews'] = read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.audit = read(PUBLIC/'usa_election_poll_release_reviews/2026/CA-primary-20261009.json')
        self.raw = [x['provider_record'] for x in self.audit['records']]

    def observations(self):
        obs, rejected = normalize(self.raw, self.policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual(len(obs), 7)
        return {o['id']: o for o in obs}

    def test_certified_ballot_keeps_all_52_house_races_and_governor_ids(self):
        races = {k:v for k,v in self.policy['races'].items() if v['state']=='CA'}
        self.assertEqual(len(races), 53)
        self.assertNotIn('USA:CA:senate', races)
        for r in races.values():
            self.assertEqual(r['ballot_competition']['candidate_count'], 2)
            self.assertFalse(r['ballot_competition']['general_unopposed'])
            self.assertFalse(r['ballot_competition']['confirmed_winner'])
            self.assertEqual(r['general_from'], '2026-06-03')
        g=self.gov['contests']['CA']
        self.assertIn('2026-general',g['source_url'])
        self.assertEqual(g['ballot_reviewed_on'],DAY)
        self.assertEqual({c['candidate_id'] for c in g['candidates']},
            {'CA:certified:2026:governor:e69ed8ee4b08b193','CA:certified:2026:governor:dd0299f5b1adba75'})

    def test_independent_and_same_party_contests_are_not_dem_gop_fabrications(self):
        self.assertEqual(self.policy['races']['USA:CA:house:06']['candidates']['Kevin Kiley']['party'],'IND')
        for district, party in [('11','DEM'),('40','REP')]:
            r=self.policy['races']['USA:CA:house:'+district]
            self.assertEqual({v['party'] for v in r['candidates'].values()},{party})
        o=self.observations()['us-202thed03f59fe']
        self.assertEqual([a['party'] for a in o['answers']],['DEM','IND'])
        self.assertFalse(o['aggregation_eligibility']['eligible'])

    def test_ppic_likely_voter_subsamples_not_all_adults_or_generic_house(self):
        obs=self.observations()
        for ident, n, total, shares in [('primary-ppic-ca-governor-20260910',1103,1745,[60,38]),
                                       ('primary-ppic-ca-governor-20260706',1003,1578,[61,36])]:
            o=obs[ident]
            self.assertEqual(o['sample_n'],n)
            self.assertEqual(o['source_quality']['question_sample_n'],n)
            self.assertEqual(o['source_quality']['disclosure_review']['total_adult_sample_n'],total)
            self.assertEqual([a['pct'] for a in o['answers']],shares)
            self.assertEqual(o['population'],'lv')
            self.assertEqual(o['race_id'],'USA:CA:governor')
        self.assertFalse(summarize(list(obs.values()),self.policy['races']['USA:CA:governor'],DAY,14)['included_ids'])

    def test_igs_registered_total_is_not_the_governor_likely_sample(self):
        o=self.observations()['gov202uc 6d968dc2']
        self.assertEqual(o['sample_n'],4512)
        self.assertEqual(o['source_quality']['disclosure_review']['total_registered_sample_n'],6989)
        self.assertEqual([a['pct'] for a in o['answers']],[58,33])
        self.assertIsNone(o['source_quality']['accuracy_grade'])

    def test_ivc_actual_answers_not_modeled_two_way_vote_or_automatic_winner(self):
        o=self.observations()['primary-ivc-ca-governor-20261002']
        self.assertEqual([a['pct'] for a in o['answers']],[48,38])
        self.assertEqual(o['sample_n'],2906)
        self.assertFalse(o['aggregation_eligibility']['eligible'])
        self.assertIn('full_question_wording_unavailable',o['aggregation_eligibility']['reasons'])
        r=self.policy['races']['USA:CA:governor']
        for days in (7,14):
            s=summarize([o],r,DAY,days)
            self.assertEqual(s['status'],'no_recent_poll')
            self.assertIsNone(s['party'])

    def test_tulchin_initial_ballot_does_not_use_informed_ballot(self):
        o=self.observations()['us-202tul5fdc419c']
        self.assertEqual([a['pct'] for a in o['answers']],[48,44])
        self.assertFalse(o['aggregation_eligibility']['eligible'])
        self.assertIsNone(o['source_quality']['question_sample_n'])
        self.assertEqual(o['answers'][1]['party'],'REP')
        self.assertIn('methodology_incomplete_reference',o['aggregation_eligibility']['reasons'])

    def test_changed_provider_and_unreviewed_future_igs_release_require_review(self):
        raw=copy.deepcopy(next(x for x in self.raw if x['id']=='gov202uc 6d968dc2'))
        raw['sample_size']=6989
        self.assertFalse(normalize([raw],self.policy,DAY)[0])
        raw=copy.deepcopy(next(x for x in self.raw if x['id']=='gov202uc 6d968dc2'))
        raw.update(id='unreviewed-next-berkeley-release',start_date='2026-10-01',end_date='2026-10-03')
        self.assertFalse(normalize([raw],self.policy,DAY)[0])

    def test_explicit_official_governor_override_is_idempotent_and_date_guarded(self):
        reviews=read(ROOT/'config/governor_matchups/2026_ballot_reviews.json')
        result=apply_ballot_reviews(self.gov,reviews,SNAPSHOT_DAY)
        self.assertEqual(result,apply_ballot_reviews(result,reviews,SNAPSHOT_DAY))
        changed=copy.deepcopy(reviews);changed['contests']['CA']['reviewed_on']='2026-10-10'
        with self.assertRaises(SourceError):apply_ballot_reviews(self.gov,changed,SNAPSHOT_DAY)

    def html(self, value='48', related='Other publication'):
        return (f'<html><nav>{related}</nav><article class="ghost-content prose"><p>'
            + f'Xavier Becerra {value}; Steve Hilton 38. '+ 'Reviewed methodology. '*10
            + '</p><script>variable noise</script></article><article>'+related+'</article></html>').encode()

    def test_html_fingerprint_ignores_recommendations_but_detects_poll_revision(self):
        self.assertEqual(primary_html_fingerprint(self.html()),primary_html_fingerprint(self.html(related='Next day news')))
        self.assertNotEqual(primary_html_fingerprint(self.html()),primary_html_fingerprint(self.html(value='49')))
        with self.assertRaises(ValueError):primary_html_fingerprint(b'<html>blocked</html>')
        with self.assertRaises(ValueError):primary_html_fingerprint(self.html()+self.html())

    def merge_html(self, body):
        snapshot=read(CONFIG/'primary_supplements_2026.json')
        entry=copy.deepcopy(next(x for x in snapshot['records'] if x['record']['id']=='primary-ivc-ca-governor-20261002'))
        entry['documents'][0]['sha256']=primary_html_fingerprint(self.html())
        class Response:
            status=200
            def geturl(self):return entry['documents'][0]['url']
            def read(self,*args):return body
            def __enter__(self):return self
            def __exit__(self,*args):return False
        snapshot['records']=[entry]
        return merge_primary_supplements([],snapshot,DAY,['CA'],opener=lambda *a,**kw:Response())

    def test_changed_html_is_preserved_as_reference_with_original_review_date(self):
        rows,receipts=self.merge_html(self.html(value='49'))
        self.assertEqual(receipts[0]['status'],'carried_forward_reference_only')
        self.assertEqual(rows[0]['answers'][0]['pct'],48)
        self.assertEqual(receipts[0]['original_reviewed_on'],DAY)
        rows,receipts=self.merge_html(self.html(related='Changed recommendations'))
        self.assertEqual(receipts[0]['status'],'primary_documents_rechecked')

    def test_same_wave_later_api_conflict_is_not_silently_merged(self):
        snapshot=read(CONFIG/'primary_supplements_2026.json')
        entry=next(x for x in snapshot['records'] if x['record']['id']=='primary-ivc-ca-governor-20261002')
        snapshot['records']=[entry]
        raw=copy.deepcopy(entry['record']);raw['id']='future-api-copy';raw['answers'][0]['pct']=57
        with self.assertRaises(ValueError):merge_primary_supplements([raw],snapshot,DAY,['CA'])

    def test_state_ie_updates_have_unique_transaction_ids_and_uncertain_phase(self):
        source=read(PUBLIC/'usa_governor_finance/2026/CA.json')
        rows=source['spending']
        self.assertTrue(rows)
        self.assertEqual(source['quality']['included_records'],len(rows))
        self.assertEqual(len({x['source_id'] for x in rows}),len(rows))
        self.assertTrue(all(x['category']=='state_independent_spender_unclassified' for x in rows))
        self.assertTrue(all(x['election_type']=='UNKNOWN' and x['reported_election_date'] is None for x in rows))
        self.assertEqual(source['last_filing_date'],max(x['filing_date'] for x in rows))

    def test_other_html_urls_are_not_wholesale_admitted(self):
        snapshot=read(CONFIG/'primary_supplements_2026.json')
        e=copy.deepcopy(next(x for x in snapshot['records'] if x['record']['id']=='primary-ivc-ca-governor-20261002'))
        e['documents'][0]['url']='https://ivn.us/a-new-unreviewed-poll/'
        snapshot['records']=[e]
        with self.assertRaises(ValueError):merge_primary_supplements([],snapshot,DAY,['CA'])
