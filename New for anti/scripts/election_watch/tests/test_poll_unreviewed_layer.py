"""Lower-confidence layer: held provider rows shown with a tier and counted only where safe."""
import unittest
from build_unreviewed_polls import build, map_answers

CANDIDATES = {'Jocelyn Benson': {'party': 'DEM', 'canonical_name': 'Jocelyn Benson'},
              'John James': {'party': 'REP', 'canonical_name': 'John James'}}


def race(observations=(), window=None):
    return {'state': 'MI', 'office': 'governor', 'district': None, 'general_from': '2026-08-05', 'candidates': CANDIDATES,
            'observations': list(observations), 'windows': {'14': window or {'status': 'no_recent_poll', 'included_ids': []}}}


def raw(id, end, d, r, **kw):
    return {'id': id, 'pollster': kw.pop('pollster', id), 'start_date': end, 'end_date': end, 'population': 'lv',
            'sample_size': 600, 'answers': [{'choice': 'Jocelyn Benson', 'pct': d}, {'choice': 'James', 'pct': r}], **kw}


def board(queue, observations=(), window=None):
    return {'as_of': '2026-10-24', 'fetched_at': 'x', 'races': {'USA:MI:governor': race(observations, window)},
            'review_queue': [{'id': i, 'race_id': 'USA:MI:governor', 'reason': reason} for i, reason in queue]}


class UnreviewedLayerTests(unittest.TestCase):
    def test_last_name_maps_to_reviewed_candidate_and_unknown_stays_unknown(self):
        out = map_answers([{'choice': 'James', 'pct': 40}, {'choice': 'Someone Else', 'pct': 3}], CANDIDATES)
        self.assertEqual((out[0]['name'], out[0]['party'], out[0]['matched']), ('John James', 'REP', 'last_name'))
        self.assertIsNone(out[1]['party'])

    def test_held_row_counts_as_low_confidence_lead_and_is_labelled(self):
        data = build(board([('m1', 'missing_sample_size')]), [raw('m1', '2026-10-18', 51, 45)], 'now')
        r = data['races']['USA:MI:governor']
        self.assertEqual(r['polls'][0]['tier'], 'unreviewed')
        self.assertEqual((r['combined_14']['status'], r['combined_14']['party']), ('single_poll_lead', 'DEM'))
        self.assertEqual(r['combined_14']['unreviewed_ids'], ['m1'])

    def test_internal_conflict_old_and_pre_general_rows_never_count(self):
        rows = [raw('i', '2026-10-20', 60, 30, internal=True), raw('c', '2026-10-20', 60, 30),
                raw('old', '2026-09-20', 60, 30), raw('pre', '2026-07-01', 60, 30)]
        data = build(board([('i', 'internal_or_partisan'), ('c', 'primary_provider_population_conflict'),
                            ('old', 'pollster_not_selected'), ('pre', 'outside_reviewed_general_period')]), rows, 'now')
        r = data['races']['USA:MI:governor']
        self.assertEqual({p['id']: p['tier'] for p in r['polls']}, {'i': 'campaign_internal', 'c': 'provider_conflict', 'old': 'unreviewed'})
        self.assertEqual(r['combined_14']['status'], 'no_recent_poll')

    def test_reviewed_poll_wins_over_same_pollster_and_reference_observation_is_layered(self):
        reviewed = {'id': 'r1', 'pollster': 'Marist', 'field_end': '2026-10-15', 'population': 'lv',
                    'answers': [{'name': 'Jocelyn Benson', 'pct': 44, 'party': 'DEM'}, {'name': 'John James', 'pct': 47, 'party': 'REP'}],
                    'aggregation_eligibility': {'eligible': True}}
        ref = {**reviewed, 'id': 'a1', 'pollster': 'ActiVote', 'field_end': '2026-10-21', 'commissioning': {},
               'answers': [{'name': 'Jocelyn Benson', 'pct': 52, 'party': 'DEM'}, {'name': 'John James', 'pct': 48, 'party': 'REP'}],
               'aggregation_eligibility': {'eligible': False, 'reasons': ['publisher_identified_release_review_pending']}}
        data = build(board([('m2', 'pollster_not_selected')], [reviewed, ref], {'status': 'single_poll_lead', 'party': 'REP', 'included_ids': ['r1']}),
                     [raw('m2', '2026-10-20', 40, 50, pollster='Marist')], 'now')
        c = data['races']['USA:MI:governor']['combined_14']
        self.assertEqual(c['reviewed_ids'], ['r1'])
        self.assertEqual(c['unreviewed_ids'], ['a1'])
        self.assertEqual((c['status'], c['lead_counts']), ('tie', {'REP': 1, 'DEM': 1}))
        tiers = {p['id']: p['tier'] for p in data['races']['USA:MI:governor']['polls']}
        self.assertEqual(tiers['a1'], 'reference_reviewed')


if __name__ == '__main__':
    unittest.main()
