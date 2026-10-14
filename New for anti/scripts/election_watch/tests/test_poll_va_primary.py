import copy
import json
from pathlib import Path
import unittest
from election_watch.va_ballot import parse_ballot
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/usa_polls'
PUBLIC=ROOT.parent.parent/'public/data'
DAY='2026-10-09'
read=lambda p:json.loads(p.read_text())

class VirginiaEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),DAY),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),DAY)
        self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/VA-primary-20261009.json')
        self.raw=[r['provider_record'] for r in self.audit['records']]
    def observations(self):
        obs,rejected=normalize(self.raw,self.policy,DAY)
        self.assertFalse(rejected);self.assertEqual(len(obs),2)
        return {r['race_id']:r for r in obs}
    def test_official_universe_38_candidates_and_no_governor_or_automatic_win(self):
        races=read(ROOT/'config/federal_matchups/2026.json')['races']
        va=[r for r in races.values() if r['state']=='VA']
        self.assertEqual(len(va),12)
        self.assertEqual(sum(len(r['candidates']) for r in va),38)
        self.assertEqual(len(races['USA:VA:senate']['candidates']),2)
        self.assertNotIn('USA:VA:governor',self.policy['races'])
        self.assertNotIn('Mark Moran',[c['name'] for c in races['USA:VA:senate']['candidates']])
        for r in va:
            self.assertEqual(r['source_role'],'state_election_agency')
            self.assertEqual(self.policy['races'][r['race_id']]['general_from'],'2026-08-05')
            self.assertFalse(self.policy['races'][r['race_id']]['ballot_competition']['general_unopposed'])
            self.assertFalse(self.policy['races'][r['race_id']]['ballot_competition']['confirmed_winner'])
    def test_primary_45_correction_keeps_provider_46_and_exact_fingerprint(self):
        raw=next(r for r in self.raw if r['subject']=='2026 VA-05')
        self.assertEqual(next(a['pct'] for a in raw['answers'] if a['choice']=='Tom Perriello'),46)
        o=self.observations()['USA:VA:house:05']
        self.assertEqual(next(a['pct'] for a in o['answers'] if a['name']=='Tom Perriello'),45)
        self.assertEqual(o['provider_answer_correction']['provider_values'],{'Tom Perriello':46})
        for field,value in [('sample_size',601),('start_date','2026-09-24'),('sponsors',['Different sponsor']),('population','rv')]:
            changed=copy.deepcopy(raw);changed[field]=value
            self.assertFalse(normalize([changed],self.policy,DAY)[0],field)
    def test_population_and_district_samples_are_not_exchanged_or_pooled(self):
        obs=self.observations()
        self.assertEqual(obs['USA:VA:house:01']['sample_n'],609)
        self.assertEqual(obs['USA:VA:house:05']['sample_n'],600)
        for o in obs.values():
            self.assertEqual(o['population'],'lv')
            self.assertEqual(o['source_quality']['question_sample_n'],o['sample_n'])
            self.assertEqual(o['source_quality']['disclosure_review']['mode']['text_to_web_pct'],26)
            self.assertIsNone(o['source_quality']['accuracy_grade'])
    def test_7_day_missing_14_day_single_source_not_confirmed_result(self):
        for rid,o in self.observations().items():
            for days in (7,14):
                result=summarize([o],self.policy['races'][rid],DAY,days)
                if days==7:
                    self.assertFalse(result['included_ids']);self.assertIsNone(result['party'])
                else:
                    self.assertEqual(result['status'],'single_poll_lead')
                    self.assertEqual(result['pollster_count'],1)
                    self.assertEqual(result['party'],'DEM' if rid.endswith('01') else 'REP')
            duplicate=copy.deepcopy(o);duplicate['id']='same-wave-second-link'
            self.assertEqual(summarize([o,duplicate],self.policy['races'][rid],DAY,14)['pollster_count'],1)
    def test_generic_informed_preprimary_and_tpsi_missing_lv_sample_stay_held(self):
        held=[r['provider_record'] for r in self.audit['held_records']]
        self.assertEqual(len(held),10)
        obs,rejected=normalize(held,self.policy,DAY)
        self.assertFalse(obs);self.assertEqual(len(rejected),10)
        lv=[r for r in held if r['pollster']=='The Public Sentiment Institute' and r['population']=='lv']
        self.assertEqual(len(lv),3);self.assertTrue(all(r['sample_size'] is None for r in lv))
        self.assertFalse(any(o['sample_n']==996 for o in self.observations().values()))
    def test_new_release_not_institution_wide_auto_approved(self):
        changed=copy.deepcopy(self.raw[0]);changed['id']='unreviewed-new-release'
        self.assertFalse(normalize([changed],self.policy,DAY)[0])
    def test_official_aliases_preserve_corroborated_fec_ids_and_missing_ids(self):
        races=read(ROOT/'config/federal_matchups/2026.json')['races']
        one=races['USA:VA:house:01']['candidates']
        self.assertEqual(next(c['candidate_id'] for c in one if c['party']=='DEM'),'H6VA01299')
        self.assertIn('Shannon Taylor',next(c for c in one if c['party']=='DEM')['poll_name_aliases'])
        baker=next(c for c in races['USA:VA:house:02']['candidates'] if c['name']=='J. Matt Baker')
        self.assertIsNone(baker['candidate_id'])
        identities=read(CONFIG/'state_finance_identities_2026.json')['races']['USA:VA:senate']
        self.assertEqual(next(r['candidate_id'] for r in identities if r['candidate_name']=='Mark R. Warner'),'S6VA00093')

class VirginiaBallotParserTests(unittest.TestCase):
    def html(self,extra=''):
        headers=['Office Title','District','Candidate Party','Candidate Name','Incumbent','Campaign Email','Campaign Address']
        rows=['<tr><td>Member, United States Senate</td><td>Statewide</td><td>Democratic</td><td>Senator</td><td>Yes</td><td>private@example.test</td><td>PRIVATE ADDRESS</td></tr>']
        rows += [f'<tr><td>Member, House of Representatives</td><td>{d}th District</td><td>Republican</td><td>Candidate {d}</td><td>No</td><td>private@example.test</td><td>PRIVATE ADDRESS</td></tr>' for d in range(1,12)]
        return '<h1>November 3, 2026 - Federal Offices</h1><table><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr>'+''.join(rows)+extra+'</table>'
    def test_private_contact_fields_not_returned_and_governor_not_created(self):
        out=parse_ballot(self.html(),DAY)
        self.assertEqual(len(out),12)
        self.assertNotIn('PRIVATE ADDRESS',json.dumps(out));self.assertNotIn('private@example.test',json.dumps(out))
        self.assertNotIn('USA:VA:governor',out)
    def test_wrong_cycle_office_party_schema_district_and_duplicates_fail_closed(self):
        duplicate='<tr><td>Member, House of Representatives</td><td>1st District</td><td>Republican</td><td>Candidate 1</td><td>No</td><td></td><td></td></tr>'
        for html in [self.html().replace('2026 - Federal','2024 - Federal'),self.html().replace('Incumbent','Status'),self.html().replace('11th District','12th District'),self.html().replace('Republican','Unknown'),self.html().replace('Member, United States Senate','Member, State Senate'),self.html(duplicate)]:
            with self.assertRaises(ValueError):parse_ballot(html,DAY)
        with self.assertRaises(ValueError):parse_ballot(self.html(),'2026-08-04')
