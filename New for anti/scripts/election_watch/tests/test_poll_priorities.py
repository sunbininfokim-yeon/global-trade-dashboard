"""Synthetic geometries check provenance, priority order and honest missingness."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from election_watch.polls import digest
from election_watch.poll_priorities import (apply_priorities, attach_coverage, geometry_location,
                                           load_finance_links, match_site)
from election_watch.live_polls import apply_watchlist, build_live
from test_live_polls import POLICY, WATCHLIST, poll, RID

DAY = '2026-10-06'
SQUARE = {'type': 'Polygon', 'coordinates': [[[-75,40],[-74,40],[-74,41],[-75,41],[-75,40]]]}


def site(state='NY'):
    value = {'id': 'fixture', 'name_ko': 'SYNTHETIC TEST ONLY', 'state': state,
             'address': '1 Fixture Street', 'address_source_url': 'https://example.org/company',
             'address_reviewed_on': DAY,
             'geocoding': {'status': 'matched', 'matched_state': state, 'retrieved_on': DAY,
                           'request_url': 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress',
                           'input_address_sha256': digest('1 Fixture Street'), 'coordinates': [-74.5,40.5]}}
    return value


def config(sites):
    return {'schema': 'usa_poll_priorities_v1', 'cycle': 2026, 'reviewed_on': DAY,
            'requested_states': ['NY'], 'priority_order': ['requested_states','cook_toss_up_and_lean','korean_company_facilities'],
            'company_scope_ko': 'SYNTHETIC TEST ONLY', 'company_sites': sites}


class PollPriorityTests(unittest.TestCase):
    def geometry_file(self, root, state='NY', district='01', **updates):
        value = {'type': 'FeatureCollection', 'source': 'SYNTHETIC 120th Congressional Districts',
                 'retrieved': DAY, 'features': [{'properties': {'state_id': state, 'district': district}, 'geometry': SQUARE}]}
        value.update(updates)
        (root/f'{state}.json').write_text(json.dumps(value))

    def test_company_address_adds_a_discovery_slot_without_inventing_a_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.geometry_file(root)
            p=apply_priorities(POLICY,config([site()]),root,DAY)
            rid='USA:NY:house:01'
            self.assertEqual(p['races'][rid]['required_candidates'], [])
            self.assertEqual(p['races'][rid]['collection_priority']['order'],1)
            b=build_live([],p,{'schema':'usa_confirmed_results_v1','results':[]},DAY,DAY,'test')
            attach_coverage(b,[],p,None)
            self.assertEqual(b['monitoring']['race_coverage'][rid]['status'],'no_provider_record')
            self.assertIsNone(b['races'][rid]['windows']['7']['party'])
            self.assertNotIn('USA:NY:senate',b['races'])
            self.assertNotIn('company_interest', POLICY)

    def test_user_regions_then_cook_then_company_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.geometry_file(root,'AL')
            p=apply_priorities(apply_watchlist(POLICY,WATCHLIST),config([site('AL')]),root,DAY)
            self.assertEqual(p['races']['USA:NY:house:17']['collection_priority']['order'],1)
            self.assertEqual(p['races']['USA:WA:house:03']['collection_priority']['order'],2)
            self.assertEqual(p['races']['USA:AL:house:01']['collection_priority']['order'],3)
            self.assertIn('AL',p['states'])

    def test_changed_address_cannot_reuse_stale_coordinates(self):
        s=site();s['address']='2 Different Street'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.geometry_file(root)
            result=match_site(s,root,120,DAY)
        self.assertIsNone(result['district']);self.assertEqual(result['mapping_reason'],'address_changed')

    def test_previous_congress_boundary_is_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.geometry_file(root,source='119th Congressional Districts')
            result=match_site(site(),root,120,DAY)
        self.assertEqual(result['mapping_reason'],'boundary_congress_mismatch')

    def test_boundary_ambiguity_is_held_instead_of_choosing_first_polygon(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.geometry_file(root)
            s=site();s['geocoding']['coordinates']=[-74.0001,40.5]
            self.assertEqual(match_site(s,root,120,DAY)['mapping_reason'],'near_district_boundary')
            data=json.loads((root/'NY.json').read_text());data['features'].append(deepcopy(data['features'][0]));
            data['features'][1]['properties']['district']='02';(root/'NY.json').write_text(json.dumps(data))
            self.assertEqual(match_site(site(),root,120,DAY)['mapping_reason'],'ambiguous_or_missing_district')

    def test_boundary_change_recomputes_company_district(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.geometry_file(root)
            before=match_site(site(),root,120,DAY)
            self.geometry_file(root,district='02')
            after=match_site(site(),root,120,DAY)
        self.assertEqual((before['district'],after['district']),('01','02'))
        self.assertNotEqual(before['boundary']['sha256'],after['boundary']['sha256'])

    def test_polygon_holes_and_multipolygons(self):
        geom=deepcopy(SQUARE);geom['coordinates'].append([[-74.6,40.4],[-74.4,40.4],[-74.4,40.6],[-74.6,40.6],[-74.6,40.4]])
        self.assertEqual(geometry_location([-74.5,40.5],geom),'outside')
        multi={'type':'MultiPolygon','coordinates':[geom['coordinates']]}
        self.assertEqual(geometry_location([-74.8,40.8],multi),'inside')

    def test_missing_geocode_keeps_statewide_join_without_guessing_house_seat(self):
        s=site();s['geocoding']={'status':'hold','reason':'address_no_unique_match'}
        with tempfile.TemporaryDirectory() as tmp:
            p=apply_priorities(POLICY,config([s]),Path(tmp),DAY)
        b=build_live([],p,{'schema':'usa_confirmed_results_v1','results':[]},DAY,DAY,'test');attach_coverage(b,[],p,None)
        joined=b['company_interest']['sites'][0]
        self.assertIsNone(joined['house_race_id'])
        self.assertEqual([r['race_id'] for r in joined['race_joins']],[RID])

    def test_empty_status_separates_pending_reviews_from_provider_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=apply_priorities(POLICY,config([]),Path(tmp),DAY)
        raw=poll(pollster='Unregistered fixture')
        b=build_live([raw],p,{'schema':'usa_confirmed_results_v1','results':[]},DAY,DAY,'test');attach_coverage(b,[raw],p,None)
        r=b['monitoring']['race_coverage'][RID]
        self.assertEqual(r['status'],'review_required');self.assertEqual(r['provider_record_count'],1)
        self.assertEqual(r['rejection_reasons'],{'pollster_not_selected':1})

    def test_finance_asset_presence_does_not_claim_governor_money_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=apply_priorities(POLICY,config([]),Path(tmp),DAY)
        b=build_live([],p,{'schema':'usa_confirmed_results_v1','results':[]},DAY,DAY,'test')
        attach_coverage(b,[],p,{'status':'loaded','generated_at':DAY,'races':{RID:{'status':'unsupported','data_file':'fixture.json'}}})
        f=b['monitoring']['race_coverage'][RID]['finance_join']
        self.assertEqual(f['status'],'unsupported');self.assertEqual(f['file'],'fixture.json')

    def test_source_and_future_coordinates_are_held(self):
        for changes, reason in [({'request_url':'https://evil.example/coordinates'},'unverified_coordinate_source'),
                                ({'retrieved_on':'2026-10-07'},'future_geocode'),
                                ({'coordinates':[float('nan'),40]},'invalid_coordinates')]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.geometry_file(root);s=site();s['geocoding'].update(changes)
                self.assertEqual(match_site(s,root,120,DAY)['mapping_reason'],reason)

    def test_reviewed_government_coordinate_fallback_is_bound_to_address(self):
        s=site();s['geocoding']={'status':'hold','reason':'address_no_unique_match'}
        s['coordinate_review']={'reviewed_on':DAY,'source_url':'https://records.tceq.texas.gov/cs/idcplg?dID=fixture',
            'source_role':'government_facility_filing','legal_entity':'SYNTHETIC','record_id':'fixture',
            'coordinate_method':'SYNTHETIC','input_address_sha256':digest(s['address']),
            'matched_state':'NY','coordinates':[-74.5,40.5]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.geometry_file(root)
            self.assertEqual(match_site(s,root,120,DAY)['coordinate_source_used'],'reviewed_government_filing')
            s['coordinate_review']['source_url']='https://example.org/unverified'
            self.assertEqual(match_site(s,root,120,DAY)['mapping_reason'],'unverified_facility_coordinate_source')

    def test_only_the_epa_owned_arcgis_layer_can_supply_facility_coordinates(self):
        s=site();s['geocoding']={'status':'hold','reason':'address_no_unique_match'}
        prefix='https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/FRS_INTERESTS/FeatureServer/0/query'
        s['coordinate_review']={'reviewed_on':DAY,'source_url':prefix+'?f=json',
            'source_role':'government_facility_registry','legal_entity':'SYNTHETIC','record_id':'fixture',
            'coordinate_method':'SYNTHETIC','input_address_sha256':digest(s['address']),
            'matched_state':'NY','coordinates':[-74.5,40.5]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.geometry_file(root)
            self.assertEqual(match_site(s,root,120,DAY)['mapping_status'],'address_point_mapped')
            s['coordinate_review']['source_url']=prefix.replace('cJ9YHowT8TU7DUyn','untrusted-owner')
            self.assertEqual(match_site(s,root,120,DAY)['mapping_reason'],'unverified_facility_coordinate_source')

    def test_conflicting_facility_points_must_agree_on_the_district(self):
        s=site();s['geocoding']['alternative_coordinates']=[[-73.5,40.5]]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.geometry_file(root)
            data=json.loads((root/'NY.json').read_text())
            other=deepcopy(data['features'][0]);other['properties']['district']='02'
            other['geometry']['coordinates']=[[[x+1,y] for x,y in ring] for ring in SQUARE['coordinates']]
            data['features'].append(other);(root/'NY.json').write_text(json.dumps(data))
            self.assertEqual(match_site(s,root,120,DAY)['mapping_reason'],'facility_coordinate_district_disagreement')
            s['geocoding']['alternative_coordinates']=[[-74.4,40.5]]
            self.assertEqual(match_site(s,root,120,DAY)['district'],'01')

    def test_finance_manifest_path_cannot_escape_public_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'index.json';p.write_text(json.dumps({'schema':'usa_election_finance_index_v1',
                'generated_at':DAY,'cycles':{'2026':{'national_file':'../outside.json'}}}))
            with self.assertRaisesRegex(ValueError,'invalid finance asset path'):
                load_finance_links(p,2026)

    def test_finance_join_requires_an_existing_matching_race_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            payloads={'index.json':{'schema':'usa_election_finance_index_v1','generated_at':DAY,
                        'cycles':{'2026':{'national_file':'national.json'}}},
                      'national.json':{'schema':'usa_election_finance_national_v1','cycle':2026,
                        'states':{'NY':{'data_file':'state.json'}}},
                      'state.json':{'cycle':2026,'state_id':'NY','races':[
                        {'race_id':RID,'status':'unsupported','data_file':'race.json'}]}}
            for name,value in payloads.items():(root/name).write_text(json.dumps(value))
            with self.assertRaises(FileNotFoundError):load_finance_links(root/'index.json',2026)
            race={'schema':'usa_election_finance_race_v1','cycle':2026,'race_id':RID,'status':'unsupported'}
            (root/'race.json').write_text(json.dumps(race))
            self.assertEqual(load_finance_links(root/'index.json',2026)['races'][RID]['status'],'unsupported')
            race['race_id']='USA:NY:senate';(root/'race.json').write_text(json.dumps(race))
            with self.assertRaisesRegex(ValueError,'finance race mismatch'):load_finance_links(root/'index.json',2026)

    def test_election_closed_does_not_advertise_old_polls_as_current_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=apply_priorities(POLICY,config([]),Path(tmp),DAY)
        b=build_live([poll()],p,{'schema':'usa_confirmed_results_v1','results':[]},'2026-11-04',DAY,'test')
        attach_coverage(b,[poll()],p,None)
        self.assertEqual(b['monitoring']['race_coverage'][RID]['status'],'election_closed')
        self.assertEqual(b['monitoring']['race_coverage'][RID]['accepted_count'],0)

if __name__ == '__main__':
    unittest.main()
