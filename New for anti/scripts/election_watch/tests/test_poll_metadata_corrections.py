"""Only exact primary-source reviews can correct aggregator metadata."""
from copy import deepcopy
import unittest
from election_watch.live_polls import normalize, provider_fingerprint, summarize
from election_watch.poll_quality import review_fingerprint
import test_poll_source_admission as admission_tests
from test_live_polls import DAY, RID

class MetadataCorrectionTests(unittest.TestCase):
    def release(self):
        raw,policy=admission_tests.SourceAdmissionTests().release()
        # Entire fixture is synthetic and never written to production data.
        raw.update(population='a',sample_size=1000)
        review=policy['quality_reviews'][raw['id']]
        review.update(question_sample_n=612,disclosure_review={'population':'LV','field_dates':[raw['start_date'],raw['end_date']]})
        review['provider_metadata_correction']={'provider_snapshot_sha256':provider_fingerprint(raw),
            'overrides':{'population':'lv','sample_size':612},'basis_ko':'SYNTHETIC PRIMARY REVIEW'}
        normalized={'id':raw['id'],'race_id':RID,'pollster_group':'local_fixture','field_start':raw['start_date'],
            'field_end':raw['end_date'],'population':'lv','sample_n':612,
            'answers':[{'name':a['choice'],'pct':a['pct'],'party':policy['races'][RID]['candidates'][a['choice']]['party']} for a in raw['answers']]}
        review['snapshot_sha256']=review_fingerprint(normalized)
        return raw,policy

    def test_primary_metadata_correction_preserves_provider_values(self):
        raw,policy=self.release();rows,rejected=normalize([raw],policy,DAY)
        self.assertFalse(rejected)
        self.assertEqual((rows[0]['population'],rows[0]['sample_n']),('lv',612))
        self.assertEqual(rows[0]['provider_metadata_correction']['provider_values'],{'population':'a','sample_size':1000})
        self.assertEqual(raw['sample_size'],1000)
        self.assertEqual(summarize(rows,policy['races'][RID],DAY,7)['pollster_count'],1)

    def test_provider_change_holds_exact_correction(self):
        for changes in [{'sample_size':999},{'end_date':'2026-09-24'},{'partisan':'DEM'},
                        {'answers':[{'choice':'Kathy Hochul','pct':49},{'choice':'Bruce Blakeman','pct':44}]}]:
            raw,policy=self.release();rows,bad=normalize([{**raw,**changes}],policy,DAY)
            self.assertFalse(rows);self.assertEqual(bad[0]['reason'],'provider_correction_snapshot_changed')

    def test_corrections_cannot_change_candidates_or_vote_percentages(self):
        raw,policy=self.release();review=policy['quality_reviews'][raw['id']]
        review['provider_metadata_correction']['overrides']['answers']=raw['answers']
        rows,bad=normalize([raw],policy,DAY)
        self.assertFalse(rows);self.assertEqual(bad[0]['reason'],'unsupported_metadata_correction')

    def test_correction_must_match_primary_disclosure_and_fingerprint(self):
        raw,policy=self.release();review=policy['quality_reviews'][raw['id']]
        review['provider_metadata_correction']['overrides']['sample_size']=500
        rows,bad=normalize([raw],policy,DAY)
        self.assertFalse(rows);self.assertEqual(bad[0]['reason'],'correction_disclosure_mismatch')

    def test_new_unreviewed_wave_is_never_corrected_or_admitted_by_old_review(self):
        raw,policy=self.release();raw['id']='synthetic-new-wave'
        rows,bad=normalize([raw],policy,DAY)
        self.assertFalse(rows);self.assertEqual(bad[0]['reason'],'pollster_not_selected')

if __name__=='__main__':unittest.main()
