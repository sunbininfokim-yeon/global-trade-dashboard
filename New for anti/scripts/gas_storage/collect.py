#!/usr/bin/env python3
"""Official gas inventories. Standard library only; no inferred stock balances.

Run: python3 collect.py --out ../../public/data/gas_storage_v1.json
GIE_API_KEY enables AGSI + ALSI. See README.md for coverage and activation.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
import zipfile

EIA_URL = 'https://ir.eia.gov/ngs/wngsr.json'
# The free snapshot above only ever carries current_week/week_ago (see
# parse_eia) -- it's a "this week's release" report, not a history endpoint.
# This is EIA's own bulk data API (v2), used only to backfill older weeks
# for the Lower 48 series; see fetch_eia_lower48_history.
EIA_V2_STORAGE_URL = 'https://api.eia.gov/v2/natural-gas/stor/wkly/data/'
AEMO_URL = 'https://nemweb.com.au/Reports/Current/GBB/GasBBActualFlowStorageLast31.CSV'
JODI_LIST = 'https://api.publisher.jodidata.org/web/files/gas'
JODI_PAGE = 'https://www.jodidata.org/gas/database/data-downloads.aspx'
ASIA = {'KR': '한국', 'JP': '일본', 'TW': '대만', 'TH': '태국', 'CN': '중국',
        'VN': '베트남', 'IN': '인도', 'ID': '인도네시아', 'MY': '말레이시아',
        'SG': '싱가포르', 'CA': '캐나다'}
EUROPE = {'EU': 'EU 합계', 'DE': '독일', 'FR': '프랑스', 'IT': '이탈리아',
          'NL': '네덜란드', 'AT': '오스트리아', 'PL': '폴란드', 'CZ': '체코',
          'ES': '스페인', 'GB': '영국', 'BE': '벨기에', 'PT': '포르투갈'}
AGSI_COUNTRIES = ['EU', 'DE', 'FR', 'IT', 'NL', 'AT', 'PL', 'CZ', 'ES', 'GB', 'REHDEN']
ALSI_COUNTRIES = ['EU', 'DE', 'FR', 'IT', 'NL', 'PL', 'ES', 'GB', 'BE', 'PT']
LIMIT = 40 * 1024 * 1024


class SourceError(Exception):
    """Only safe categorical errors are written to public output."""


def number(raw):
    if raw is None or isinstance(raw, bool) or str(raw).strip() in ('', '-', '--', 'NA', 'N/A', 'null'):
        return None
    try:
        value = float(str(raw).replace(',', ''))
    except (TypeError, ValueError):
        raise SourceError('invalid_number') from None
    if not math.isfinite(value):
        raise SourceError('nonfinite_number')
    return value


def stock(raw):
    value = number(raw)
    if value is not None and value < 0:
        raise SourceError('negative_inventory')
    return value


def period_date(period):
    if re.fullmatch(r'\d{4}-\d{2}', period):
        y, m = map(int, period.split('-'))
        return date(y, m, calendar.monthrange(y, m)[1])
    return date.fromisoformat(period)


def get_bytes(url, headers=None):
    # Never return/log exception text: URLs or upstream errors can contain keys.
    for attempt in range(3):
        try:
            request = Request(url, headers={'User-Agent': 'ChokeMonitor-GasStorage/1.0', **(headers or {})})
            with urlopen(request, timeout=45) as response:
                body = response.read(LIMIT + 1)
            if len(body) > LIMIT:
                raise SourceError('response_too_large')
            return body
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise SourceError(f'http_{exc.code}') from None
        except (URLError, TimeoutError, OSError):
            if attempt == 2:
                raise SourceError('network_error') from None
        time.sleep(2 ** attempt)
    raise SourceError('network_error')


def decode_json(body):
    try:
        return json.loads(body.decode('utf-8-sig'))
    except (ValueError, UnicodeError):
        raise SourceError('invalid_json') from None


def series(sid, provider, country, label, kind, unit, frequency, scope, observations):
    return dict(id=sid, provider=provider, country=country, label_ko=label,
                storage_type=kind, unit=unit, frequency=frequency, coverage=scope,
                observations=observations, status='ok')


def parse_eia(body):
    payload = decode_json(body)
    if payload.get('periodicity') != 'weekly' or not payload.get('series'):
        raise SourceError('eia_schema_changed')
    result = []
    for row in payload['series']:
        if row.get('unitsshort', '').lower() != 'bcf':
            raise SourceError('eia_unit_changed')
        observations = []
        for i, (period, value) in enumerate(row['data']):
            # The year-ago comparison is not a contiguous weekly history point.
            if period not in (payload['current_week'], payload['week_ago']):
                continue
            obs = dict(period=period, value=stock(value), source_quality='official_estimate',
                       revision_flag=row.get('revision_flag', [])[i],
                       reclassification_flag=row.get('reclassification_flag', [])[i])
            if period == payload['current_week']:
                obs['comparisons'] = row.get('calculated', {})
                obs['year_ago_value'] = next((stock(v) for d, v in row['data'] if d == payload['year_ago']), None)
            observations.append(obs)
        result.append(series(row['series_id'], 'eia', 'US', '미국 본토 48개 주' if row['series_id'] == 'png.nw2_epg0_swo_r48_bcf.w' else row['name'],
                             'underground_working_gas', 'Bcf', 'weekly',
                             'Lower 48; regional rows overlap with total and must not be summed together', observations))
    return result


def fetch_eia_lower48_history(fetch, api_key, weeks=280):
    """Best-effort backfill for the Lower 48 series beyond the two points
    parse_eia gets from the free snapshot report. Purely additive: the
    caller merges this in underneath the primary snapshot's own points,
    which always win on an overlapping period (see collect()). Same EIA v2
    bulk API and facet[series][] convention collect_benchmarks already uses
    for Henry Hub (RNGWHHD) -- NW2_EPG0_SWO_R48_BCF is the same series_id
    the free wngsr.json snapshot reports (as 'png.nw2_epg0_swo_r48_bcf.w'),
    just without the provider prefix and frequency suffix the v2 facet
    doesn't take. A fetch failure here can never make the primary EIA
    source worse, only leave this one series short on history for longer.
    """
    params = {
        'api_key': api_key,
        'frequency': 'weekly',
        'data[0]': 'value',
        'facets[series][]': 'NW2_EPG0_SWO_R48_BCF',
        'sort[0][column]': 'period',
        'sort[0][direction]': 'desc',
        'length': min(weeks, 5000),
    }
    body = fetch(EIA_V2_STORAGE_URL + '?' + urlencode(params))
    rows = decode_json(body).get('response', {}).get('data')
    if not isinstance(rows, list) or not rows:
        raise SourceError('eia_v2_empty')
    out = []
    for row in rows:
        if row.get('series') != 'NW2_EPG0_SWO_R48_BCF' or str(row.get('units', '')).upper() != 'BCF':
            raise SourceError('eia_v2_series_or_unit_changed')
        period, value = row.get('period'), row.get('value')
        if not period or value is None:
            continue
        out.append(dict(period=period, value=stock(value), source_quality='official_estimate'))
    if not out:
        raise SourceError('eia_v2_no_rows')
    return out


def parse_aemo(body):
    reader = csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
    required = {'FacilityId', 'FacilityType', 'HeldInStorage', 'GasDate', 'LastUpdated', 'CushionGasStorage'}
    if not required.issubset(reader.fieldnames or []):
        raise SourceError('aemo_schema_changed')
    grouped = {}
    for row in reader:
        if row['FacilityType'] != 'STOR':
            continue
        sid = 'aemo:' + row['FacilityId']
        if sid not in grouped:
            grouped[sid] = (row, {})
        period = row['GasDate'].replace('/', '-')
        point = dict(period=period, value=stock(row['HeldInStorage']),
                     cushion_gas_tj=stock(row['CushionGasStorage']),
                     source_updated_at=row['LastUpdated'], source_quality='operator_reported')
        previous = grouped[sid][1].get(period)
        if previous and previous['source_updated_at'] == point['source_updated_at'] and previous != point:
            raise SourceError('aemo_conflicting_duplicate')
        if previous is None or point['source_updated_at'] > previous['source_updated_at']:
            grouped[sid][1][period] = point
    if not grouped:
        raise SourceError('aemo_no_storage_rows')
    # Do not total mixed facilities or subtract cushion gas without a verified basis.
    return [series(sid, 'aemo', 'AU', row['FacilityName'], 'facility_reported_storage', 'TJ', 'daily',
                   'Named GBB facility only; not Australia total; cushion gas reported separately', list(points.values()))
            for sid, (row, points) in grouped.items()]


def parse_jodi(body):
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
        members = [x for x in archive.infolist() if x.filename.lower().endswith('.csv')]
        if len(members) != 1 or members[0].file_size > LIMIT:
            raise SourceError('jodi_archive_schema_changed')
        reader = csv.DictReader(io.TextIOWrapper(archive.open(members[0]), encoding='utf-8-sig'))
        required = {'REF_AREA', 'TIME_PERIOD', 'ENERGY_PRODUCT', 'FLOW_BREAKDOWN', 'UNIT_MEASURE', 'OBS_VALUE', 'ASSESSMENT_CODE'}
        if not required.issubset(reader.fieldnames or []):
            raise SourceError('jodi_schema_changed')
        groups = {c: {} for c in ASIA}
        for row in reader:
            c = row['REF_AREA']
            if c not in groups or row['ENERGY_PRODUCT'] != 'NATGAS' or row['FLOW_BREAKDOWN'] != 'CLOSTLV' or row['UNIT_MEASURE'] != 'M3':
                continue
            p = row['TIME_PERIOD']
            value = stock(row['OBS_VALUE'])
            point = dict(period=p, value=value, source_quality=row['ASSESSMENT_CODE'])
            # Conservative publication rule, not a reinterpretation of JODI code 3.
            if value == 0 and row['ASSESSMENT_CODE'] != '1':
                point.update(value=None, reported_value=0, quality_note='zero_requires_verification')
            if p in groups[c] and groups[c][p] != point:
                raise SourceError('jodi_conflicting_duplicate')
            groups[c][p] = point
    except (zipfile.BadZipFile, UnicodeError):
        raise SourceError('invalid_jodi_archive') from None
    if not groups['KR'] or not groups['JP']:
        raise SourceError('jodi_core_series_missing')
    return [series('jodi:' + c, 'jodi', c, label + ' 월말 천연가스 재고',
                   'national_closing_stocks', 'million_m3_gas', 'monthly',
                   'JODI national territory closing stocks; gas equivalent, not LNG liquid tank volume or capacity', list(groups[c].values()))
            for c, label in ASIA.items()]


def gie_series(platform, country, observations):
    return series(f'{platform}:{country}', platform, 'DE' if country == 'REHDEN' else country,
                  'Rehden 지하 가스 저장시설' if country == 'REHDEN' else EUROPE[country],
                  'underground_working_gas' if platform == 'agsi' else 'lng_terminal_inventory',
                  'TWh' if platform == 'agsi' else 'thousand_m3_LNG', 'daily',
                  ('UGS Rehden facility EIC 21Z000000000271O; included in Germany aggregate' if country == 'REHDEN' else
                   'GIE reporting aggregate; EU and country rows overlap; AGSI and ALSI have different physical bases'), observations)


def parse_gie(payload, platform, country, expected_code=None):
    if payload.get('error'):
        raise SourceError('gie_access_or_api_error')
    if not isinstance(payload.get('data'), list):
        raise SourceError('gie_schema_changed')
    observations = []
    for row in payload['data']:
        if str(row.get('code', '')).upper() != (expected_code or country).upper():
            raise SourceError('gie_wrong_aggregate')
        field, cap = ('gasInStorage', 'workingGasVolume') if platform == 'agsi' else ('inventory', 'dtmi')
        if field not in row or 'gasDayStart' not in row:
            raise SourceError('gie_schema_changed')
        # Current ALSI returns {lng: thousand liquid m3, gwh: energy} objects.
        raw_value, raw_capacity = row[field], row.get(cap)
        if platform == 'alsi':
            if not isinstance(raw_value, dict) or 'lng' not in raw_value:
                raise SourceError('alsi_unit_schema_changed')
            if not isinstance(raw_capacity, dict) or 'lng' not in raw_capacity:
                raise SourceError('alsi_capacity_schema_changed')
            raw_value, raw_capacity = raw_value['lng'], raw_capacity['lng']
        value = None if row.get('status') == 'N' else stock(raw_value)
        capacity = stock(raw_capacity)
        obs = dict(period=row['gasDayStart'], value=value, capacity=capacity,
                   source_quality=row.get('status', 'unspecified'),
                   covered_capacity_pct=number(row.get('coveredCapacity')),
                   source_updated_at=row.get('updatedAt'),
                   fill_pct=(number(row.get('full')) if platform == 'agsi' else
                             (round(value / capacity * 100, 4) if value is not None and capacity else None)))
        if platform == 'agsi':
            obs.update(injection_gwh_day=number(row.get('injection')), withdrawal_gwh_day=number(row.get('withdrawal')))
        else:
            obs['sendout_gwh_day'] = number(row.get('sendOut'))
        observations.append(obs)
    if not observations:
        raise SourceError('gie_empty_response')
    return gie_series(platform, country, observations)


def fetch_gie(platform, country, today, fetch):
    key = os.environ.get('GIE_API_KEY')
    if not key:
        item = gie_series(platform, country, [])
        item.update(status='requires_key', error_code='GIE_API_KEY_missing')
        return item, []
    points, evidence = [], []
    facility_params = {}
    expected_code = None
    if country == 'REHDEN':
        listing_url = 'https://agsi.gie.eu/api/about?show=listing'
        raw = fetch(listing_url, {'x-key': key})
        listing = decode_json(raw)
        if not isinstance(listing, list):
            raise SourceError('gie_listing_schema_changed')
        matches = [f for operator in listing for f in operator.get('facilities', [])
                   if f.get('eic') == '21Z000000000271O' and not f.get('operational_end_date')]
        if len(matches) != 1:
            raise SourceError('rehden_identity_ambiguous')
        f = matches[0]
        facility_params = {'country': f['country'], 'company': f['company'], 'facility': f['eic']}
        expected_code = f['eic']
        evidence.append(provenance(listing_url, raw))
    for page in range(1, 11):
        params = {'type' if country == 'EU' else 'country': country.lower(),
                  'from': (today - timedelta(days=190)).isoformat(), 'to': today.isoformat(),
                  'size': 300, 'page': page}
        params.update(facility_params)
        url = f'https://{platform}.gie.eu/api?' + urlencode(params)
        time.sleep(1.1)  # Stay below GIE's documented 60 calls/minute.
        raw = fetch(url, {'x-key': key})
        payload = decode_json(raw)
        item = parse_gie(payload, platform, country, expected_code)
        points.extend(item['observations'])
        evidence.append(provenance(url, raw))
        if int(payload.get('last_page', 1)) <= page:
            item['observations'] = points
            return item, evidence
    raise SourceError('gie_pagination_limit')


def provenance(url, body):
    return {'url': url, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}


def collect_benchmarks(fetch, previous, today):
    """Prices have a separate contract: never pretend a trading hub is a tank."""
    public_url = 'https://www.eia.gov/dnav/ng/hist/rngwhhda.htm'
    henry = dict(id='henry_hub_spot', label_ko='Henry Hub 현물', unit='USD/MMBtu',
                 instrument_type='spot', frequency='daily', stale_after_days=10, source='EIA', source_url=public_url,
                 status='requires_key', observations=[], latest=None)
    key = os.environ.get('EIA_API_KEY')
    if key:
        try:
            params = {'api_key': key, 'frequency': 'daily', 'data[0]': 'value',
                      'facets[series][]': 'RNGWHHD', 'sort[0][column]': 'period',
                      'sort[0][direction]': 'desc', 'length': 260}
            body = fetch('https://api.eia.gov/v2/natural-gas/pri/fut/data/?' + urlencode(params))
            rows = decode_json(body)['response']['data']
            if not rows:
                raise SourceError('henry_empty_response')
            for row in rows:
                if row.get('series') != 'RNGWHHD' or row.get('units') != '$/MMBTU':
                    raise SourceError('henry_series_or_unit_changed')
                if period_date(row['period']) > today:
                    raise SourceError('future_observation')
            points = sorted([dict(period=r['period'], value=number(r['value'])) for r in rows], key=lambda p: p['period'])
            henry.update(observations=points, latest=points[-1], status='ok',
                         evidence=provenance(public_url, body))
            if points[-1]['value'] is None:
                henry['status'] = 'partial'
            elif (today - period_date(points[-1]['period'])).days > 10:
                henry['status'] = 'stale'
        except (SourceError, KeyError, ValueError, TypeError) as exc:
            henry.update(status='error', error_code=str(exc) if isinstance(exc, SourceError) else 'schema_changed')
            old = next((p for p in previous.get('benchmarks', []) if p['id'] == henry['id']), {})
            henry.update(observations=old.get('observations', []), latest=old.get('latest'))
    if henry['status'] == 'requires_key':
        old = next((p for p in previous.get('benchmarks', []) if p['id'] == henry['id']), {})
        henry.update(observations=old.get('observations', []), latest=old.get('latest'))
    ttf = dict(id='ttf', label_ko='TTF', unit=None, instrument_type=None,
               source=None, source_url='https://www.ice.com/global-natural-gas-futures/ttf',
               status='provider_required', observations=[], latest=None,
               note_ko='API 제공업체 및 현물·선물 계약 기준 확인 필요')
    return [henry, ttf]


def finalize(item, previous, today):
    old = previous.get(item['id'], {})
    # JODI full snapshots are authoritative: removed observations stay removed.
    merge_old = item['provider'] != 'jodi' or item['status'] == 'error'
    points = {p['period']: p for p in old.get('observations', [])} if merge_old else {}
    for point in item['observations']:
        if period_date(point['period']) > today:
            raise SourceError('future_observation')
        points[point['period']] = point
    ordered = sorted(points.values(), key=lambda p: p['period'])[-400:]
    item['observations'] = ordered
    latest = ordered[-1] if ordered else None
    item['latest'] = latest
    item['change'] = None
    item['change_period'] = {'daily': 'day_on_day', 'weekly': 'week_on_week', 'monthly': 'month_on_month'}[item['frequency']]
    if len(ordered) >= 2 and all(p['value'] is not None for p in ordered[-2:]):
        a, b = ordered[-2:]
        da, db = period_date(a['period']), period_date(b['period'])
        contiguous = ((db - da).days == {'daily': 1, 'weekly': 7}.get(item['frequency'])
                      if item['frequency'] != 'monthly' else db.year * 12 + db.month - da.year * 12 - da.month == 1)
        if contiguous:
            item['change'] = round(b['value'] - a['value'], 6)
    threshold = {'daily': 4, 'weekly': 15, 'monthly': 120}[item['frequency']]
    age = (today - period_date(latest['period'])).days if latest else None
    item['age_days'] = age
    item['freshness'] = 'missing' if latest is None else 'stale' if age > threshold else 'current_for_cadence'
    if item['status'] == 'ok':
        if latest is None:
            item['status'] = 'unsupported'
        elif age > threshold:
            item['status'] = 'stale'
        elif latest['value'] is None or latest.get('source_quality') not in ('1', 'C', 'official_estimate', 'operator_reported'):
            item['status'] = 'partial'
    if item['status'] in ('error', 'requires_key'):
        item['change'] = None
        item['retained_previous_observations'] = bool(ordered)
    return item


def collect(previous=None, today=None, fetch=get_bytes):
    today = today or datetime.now(timezone.utc).date()
    previous = previous or {}
    old = {r['id']: r for r in previous.get('series', [])}
    items, sources = [], []
    for provider, url, parser in [('eia', EIA_URL, parse_eia), ('aemo', AEMO_URL, parse_aemo), ('jodi', JODI_LIST, parse_jodi)]:
        try:
            body = fetch(url)
            ev = [provenance(url, body)]
            if provider == 'jodi':
                listing = decode_json(body)
                files = [x for x in listing['files'] if x['format'] == 'CSV' and not x.get('ignore')]
                if len(files) != 1 or not isinstance(listing['publicationId'], int):
                    raise SourceError('jodi_listing_changed')
                filename = files[0]['filename']
                if not re.fullmatch(r'[A-Za-z0-9_.-]+\.zip', filename):
                    raise SourceError('jodi_filename_invalid')
                url = f'https://www.jodidata.org/jodi-publisher/gas/{listing["publicationId"]}/{quote(filename)}'
                body = fetch(url)
                ev.append(provenance(url, body))
            parsed = [finalize(r, old, today) for r in parser(body)]
            items.extend(parsed)
            sources.append(dict(provider=provider, status='ok', evidence=ev))
        except (SourceError, ValueError, KeyError, TypeError, IndexError) as exc:
            code = str(exc) if isinstance(exc, SourceError) else 'schema_changed'
            sources.append(dict(provider=provider, status='error', error_code=code))
            for r in old.values():
                if r['provider'] == provider:
                    items.append(finalize({**r, 'observations': [], 'status': 'error', 'error_code': code}, old, today))

    # Best-effort backfill for the Lower 48 series: the primary EIA snapshot
    # above only ever carries two points, so on its own this series would
    # take ~5 years of daily cron runs to reach the same depth the other
    # sources already have. Recorded as its own source entry -- a failure
    # here never touches the primary 'eia' source's own status above, only
    # leaves this one series short on history for longer.
    eia_key = os.environ.get('EIA_API_KEY')
    lower48 = next((it for it in items if it['id'] == 'png.nw2_epg0_swo_r48_bcf.w'), None)
    if eia_key and lower48 is not None:
        try:
            history = fetch_eia_lower48_history(fetch, eia_key)
            # Backfill first, primary snapshot points second, so finalize's
            # period-keyed merge lets the primary (authoritative) points win
            # on any overlapping week.
            lower48['observations'] = history + lower48['observations']
            finalize(lower48, old, today)
            sources.append(dict(provider='eia_v2_backfill', status='ok', added=len(history)))
        except (SourceError, ValueError, KeyError, TypeError, IndexError) as exc:
            code = str(exc) if isinstance(exc, SourceError) else 'schema_changed'
            sources.append(dict(provider='eia_v2_backfill', status='error', error_code=code))

    for platform, countries in [('agsi', AGSI_COUNTRIES), ('alsi', ALSI_COUNTRIES)]:
        for country in countries:
            try:
                item, ev = fetch_gie(platform, country, today, fetch)
                item = finalize(item, old, today)
                sources.append(dict(provider=platform, country=country,
                                    status='requires_key' if item['status'] == 'requires_key' else 'ok', evidence=ev))
            except (SourceError, ValueError, TypeError, KeyError) as exc:
                code = str(exc) if isinstance(exc, SourceError) else 'schema_changed'
                item = gie_series(platform, country, [])
                item.update(status='error', error_code=code)
                item = finalize(item, old, today)
                sources.append(dict(provider=platform, country=country, status='error', error_code=code))
            items.append(item)
    benchmarks = collect_benchmarks(fetch, previous, today)
    return dict(schema_version='gas_storage_v1', fetched_at=datetime.now(timezone.utc).isoformat(),
                as_of=today.isoformat(), status='partial' if any(s['status'] != 'ok' for s in sources) or any(b['status'] != 'ok' for b in benchmarks) else 'ok',
                sources=sources, series=sorted(items, key=lambda r: r['id']),
                benchmarks=benchmarks,
                notes=['Inventories are not capacity, geological reserves, or strategic government reserves.',
                       'No global total: geographies, physical bases and observation dates overlap or differ.',
                       'Monthly JODI values use million cubic metres of gas, not liquid LNG cubic metres.',
                       'Previous snapshots are retained after source errors; status and fetched_at are not observation dates.',
                       'Historical series are revised snapshots, not a point-in-time backtest dataset.'])


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        f.write(text)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[2] / 'public/data/gas_storage_v1.json')
    parser.add_argument('--require-gie', action='store_true', help='Fail health check if GIE key/access is unavailable')
    args = parser.parse_args()
    previous = json.loads(args.out.read_text()) if args.out.exists() else {}
    result = collect(previous)
    atomic_write(args.out, result)
    failures = [s for s in result['sources'] if s['status'] == 'error' or (args.require_gie and s['status'] != 'ok')]
    failures.extend(p for p in result['benchmarks'] if p['status'] in ('error', 'requires_key'))
    print(json.dumps({'series': len(result['series']), 'status': result['status'], 'failed_sources': len(failures)}))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
