import csv,io
import unittest
from election_watch.governor_tn import HEADERS,parse_export,summarize_exports
from election_watch.superpac import SourceError


def encoded(rows,headers=HEADERS):
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=headers)
    writer.writeheader();writer.writerows(rows);return output.getvalue().encode()


class TennesseeAuditTests(unittest.TestCase):
    def fixture(self):
        row=dict.fromkeys(HEADERS,'');row.update({'Type':'Independent','Adj':'N','Amount':'$100.00',
            'Date':'06/10/2026','Candidate/PAC Name':'Fixture PAC','Candidate For':'ALPHA, CANDIDATE','S/O':'S'})
        roster=[{'candidate_id':'TN:fixture','name':'Candidate Alpha','party':'DEM'}]
        snapshot={2025:{'csv':encoded([]),'expected_count':0,'export_url':'https://apps.tn.gov/fixture'},
                  2026:{'csv':encoded([row,row]),'expected_count':2,'export_url':'https://apps.tn.gov/fixture'}}
        return row,roster,snapshot

    def test_real_duplicate_rows_are_held_and_never_zero_or_sum(self):
        _,roster,snapshot=self.fixture()
        payload=summarize_exports(2026,snapshot,roster,'2026-10-08T00:00:00Z')
        self.assertEqual(payload['current_governor_target_records'],2)
        candidate=payload['candidate_audits'][0]
        self.assertEqual(candidate['ambiguous_identical_rows'],2)
        self.assertIsNone(candidate['support_cents']);self.assertIsNone(candidate['oppose_cents'])
        self.assertEqual(payload['status'],'collected_normalization_held')

    def test_source_count_must_match_whole_export(self):
        row,_,_=self.fixture()
        with self.assertRaises(SourceError):parse_export(encoded([row]),2)

    def test_declared_legacy_encoding_is_preserved_and_unknown_encoding_fails(self):
        row,_,_=self.fixture();row['Purpose']='Fianc\u00e9'
        raw=encoded([row]).decode().encode('iso-8859-1')
        self.assertEqual(parse_export(raw,1,'iso-8859-1')[0]['Purpose'],row['Purpose'])
        with self.assertRaises(SourceError):parse_export(raw,1)
        with self.assertRaises(SourceError):parse_export(raw,1,'unknown-codec')

    def test_column_drift_or_regular_contribution_is_not_ie(self):
        row,_,_=self.fixture()
        with self.assertRaises(SourceError):parse_export(encoded([],HEADERS[:-1]),0)
        row['Type']='Monetary'
        with self.assertRaises(SourceError):parse_export(encoded([row]),1)

    def test_target_name_requires_exact_reviewed_reverse_name(self):
        row,roster,snapshot=self.fixture();row['Candidate For']='ALPHA, OTHER'
        snapshot[2026].update(csv=encoded([row]),expected_count=1)
        result=summarize_exports(2026,snapshot,roster,'2026-10-08T00:00:00Z')
        self.assertEqual(result['current_governor_target_records'],0)
        self.assertIsNone(result['candidate_audits'][0]['support_cents'])

    def test_both_report_years_and_reviewed_candidates_required(self):
        _,roster,snapshot=self.fixture()
        with self.assertRaises(SourceError):summarize_exports(2026,{2026:snapshot[2026]},roster,'2026-10-08T00:00:00Z')
        with self.assertRaises(SourceError):summarize_exports(2026,snapshot,[],'2026-10-08T00:00:00Z')

    def test_duplicate_candidate_names_do_not_choose_a_target(self):
        _,roster,snapshot=self.fixture()
        with self.assertRaises(SourceError):summarize_exports(2026,snapshot,roster*2,'2026-10-08T00:00:00Z')

    def test_malformed_or_extra_csv_columns_are_not_silently_dropped(self):
        row,_,_=self.fixture();raw=encoded([row])+b'Independent,N,$10,01/01/2026,,,,,,,,extra\n'
        with self.assertRaises(SourceError):parse_export(raw,2)
