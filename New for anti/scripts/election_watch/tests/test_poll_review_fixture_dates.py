"""Later unrelated roster reviews must not advance historical poll scenarios."""
from copy import deepcopy
import importlib
import unittest
from unittest.mock import patch
from tests.poll_config_fixture import SNAPSHOT_DAY
from election_watch.live_polls import normalize

CASES=(('test_poll_fl_recent_20261014','FloridaRecentTests'),
 ('test_poll_me_primary','MaineEvidenceTests'),('test_poll_mn_recent_20261014','MinnesotaRecentTests'),
 ('test_poll_nc_recent_20261014','NorthCarolinaRecentTests'),('test_poll_tx_recent_20261014','TexasRecentTests'))
class ReviewFixtureDateTests(unittest.TestCase):
 def test_later_other_state_catalog_review_keeps_each_original_poll_capture_day(self):
  day=max(SNAPSHOT_DAY,'2026-10-16')
  for name,klass in CASES:
   with self.subTest(module=name):
    module=importlib.import_module('tests.'+name);original_read=module.read
    def later(path):
     value=original_read(path)
     if path.name=='ballot_reviews_2026.json':
      value=deepcopy(value);value['races']['USA:MT:senate']['reviewed_on']=day
     return value
    original_packet=next(p for p in module.packets() if p['state']=={'test_poll_fl_recent_20261014':'FL','test_poll_me_primary':'ME','test_poll_mn_recent_20261014':'MN','test_poll_nc_recent_20261014':'NC','test_poll_tx_recent_20261014':'TX'}[name])
    with patch.object(module,'read',side_effect=later),patch.object(module,'SNAPSHOT_DAY',day):
     cls=getattr(module,klass);cls.setUpClass()
    self.assertEqual(cls.policy['races']['USA:MT:senate']['ballot_review']['reviewed_on'],day)
    self.assertEqual(cls.packet['capture']['as_of'],original_packet['capture']['as_of'])
    self.assertEqual(cls.packet['capture']['fetched_at'],original_packet['capture']['fetched_at'])
 def test_new_catalog_clock_does_not_admit_future_primary_review_to_old_poll_scenario(self):
  module=importlib.import_module('tests.test_poll_mn_recent_20261014');cls=module.MinnesotaRecentTests;cls.setUpClass()
  policy=deepcopy(cls.policy);policy['quality_reviews'][cls.raw['id']]['reviewed_on']='2026-10-16'
  rows,held=normalize([cls.raw],policy,'2026-10-14')
  self.assertFalse(rows);self.assertEqual(held[0]['reason'],'future_quality_review')
