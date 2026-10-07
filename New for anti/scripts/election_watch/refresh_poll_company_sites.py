#!/usr/bin/env python3
"""Explicit refresh of reviewed business addresses via the keyless Census geocoder.

This is separate from daily polling; it changes the reviewed coordinate snapshot.
District joins are recomputed by refresh_live_polls against current boundaries.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from election_watch.polls import atomic, digest, read, require

ROOT = Path(__file__).resolve().parent
ENDPOINT = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'


def geocode(site, checked):
    import json
    # Postal routing ZIPs can differ from Census street ranges. Retry the same
    # street/city/state without ZIP; never substitute a city centroid.
    matches = []
    queries = [(site['address'], site['address_source_url']),
               (site['address'].rsplit(' ', 1)[0], site['address_source_url'])]
    for alternative in site.get('address_alternatives', []):
        require(alternative['reviewed_on'] <= checked and alternative['source_url'].startswith('https://'),
                'unreviewed_address_alternative')
        queries.append((alternative['address'], alternative['source_url']))
    for address, address_source in queries:
        query = ENDPOINT+'?'+urlencode({'address': address, 'benchmark': 'Public_AR_Current', 'format': 'json'})
        with urlopen(Request(query, headers={'User-Agent': 'ElectionPollPipeline/2.0'}), timeout=20) as response:
            require(response.url.startswith(ENDPOINT), 'unexpected_geocoder_redirect')
            data = json.load(response)
        matches = data['result']['addressMatches']
        if matches:
            break
    require(len(matches) == 1, 'address_no_unique_match')
    match = matches[0]
    require(match['addressComponents']['state'] == site['state'], 'geocoder_state_mismatch')
    require(match['matchedAddress'].split(' ', 1)[0] == address.split(' ', 1)[0], 'house_number_mismatch')
    return {'status': 'matched', 'input_address_sha256': digest(site['address']), 'request_url': query,
            'query_address': address, 'query_address_source_url': address_source, 'retrieved_on': checked, 'matched_address': match['matchedAddress'],
            'matched_state': match['addressComponents']['state'],
            'coordinates': [match['coordinates']['x'], match['coordinates']['y']],
            'tiger_line': match.get('tigerLine'), 'benchmark': data['result']['input']['benchmark'],
            'response_sha256': digest(data), 'coordinate_method': 'Census address-range interpolation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'config/usa_polls/priorities_2026.json')
    parser.add_argument('--site', action='append', help='Limit refresh to these reviewed site IDs')
    args = parser.parse_args()
    config = read(args.config)
    require(config['schema'] == 'usa_poll_priorities_v1', 'priority schema')
    checked = datetime.now(timezone.utc).date().isoformat()
    held = 0
    for site in config['company_sites']:
        if args.site and site['id'] not in args.site:
            continue
        try:
            site['geocoding'] = geocode(site, checked)
            site.pop('geocoding_refresh_error', None)
            print(site['id'], site['geocoding']['matched_address'])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            held += 1
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            # A transient failure never silently erases a reviewed coordinate.
            if site.get('geocoding', {}).get('status') == 'matched':
                site['geocoding_refresh_error'] = {'checked_on': checked, 'reason': reason}
            else:
                site['geocoding'] = {'status': 'hold', 'retrieved_on': checked, 'reason': reason}
            print(site['id'], 'hold:', reason)
    atomic(args.config, config)
    print({'sites': len(config['company_sites']), 'held_or_failed_refresh': held})
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
