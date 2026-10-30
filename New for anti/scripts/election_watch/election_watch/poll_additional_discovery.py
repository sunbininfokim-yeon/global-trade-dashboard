"""Publisher-declared public embeds and RSS; never automatic poll admission."""
from collections import Counter
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import hashlib
import json
import re
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from .polls import digest, require
from .poll_source_discovery import safe_link

RTWH = 'https://www.racetothewh.com/allpolls'
RSS = 'https://audioboom.com/channels/5174627.rss'
EMBED = 'https://e.infogram.com/_/HZeNWKobFtZDUUB2Xuyr?src=embed&embed_type=responsive_iframe'
LIVE_BASE = 'https://live-data.jifo.co/'
LIMIT = 4_000_000


def fetch(url, stamp, health, key, opener):
    try:
        with opener(Request(url, headers={'User-Agent': 'ElectionEvidenceReview/1.0'}), timeout=20) as response:
            require(response.url == url, 'unexpected discovery redirect')
            body = response.read(LIMIT+1)
            require(len(body) <= LIMIT, 'oversized supplemental discovery')
        health[key] = {'status': 'fetched', 'url': url, 'captured_at': stamp,
                       'sha256': hashlib.sha256(body).hexdigest()}
        return body
    except (OSError, ValueError) as exc:
        health[key] = {'status': 'unavailable', 'url': url, 'attempted_at': stamp,
                       'error_type': type(exc).__name__}
        return None


def live_key(html):
    marker = 'window.infographicData='
    require(html.count(marker) == 1, 'changed published Infogram manifest')
    doc, _ = json.JSONDecoder().raw_decode(html.split(marker, 1)[1])
    require('2026' in doc['title'], 'changed published chart election cycle')
    # This embed is explicitly published by RTWH. Read only its displayed chart;
    # do not access the original Google Drive sheet or editor/private URLs.
    entities = doc['elements']['content']['content']['entities']
    live = [e.get('props', {}).get('chartData', {}).get('custom', {}).get('live')
            for e in entities.values()]
    live = [x for x in live if x and x.get('enabled')]
    require(len(live) == 1 and live[0]['provider'] == 'atlas_google_drive'
            and re.fullmatch('[0-9a-f-]{36}', live[0]['key']), 'changed published live chart')
    return live[0]['key']


def text(cell):
    return cell.get('value', '') if isinstance(cell, dict) else cell or ''


def parse_rtwh(payload, cycle, state_names):
    data = payload['data']
    require(isinstance(data, list) and 1 <= len(data) <= 2 and 1 < len(data[0]) <= 5000,
            'changed RTWH live table')
    # The publisher has two display sheets for the same rows. Select the
    # reviewed first sheet once; do not count its alternate rendering twice.
    if len(data) == 2:
        require(data[1][0] == ['Added', 'Section', 'Type', 'Poll (With Links)', 'Leader', 'Data']
                and len(data[1]) == len(data[0]), 'changed RTWH alternate display sheet')
    table = data[0]
    require(table[0] == ['Added', 'Section (Links)', 'Type', 'Poll (Links)', 'Leader', 'Data'],
            'changed RTWH columns')
    records = []; skipped = []; office = None; added = None
    for index, row in enumerate(table[1:]):
        try:
            require(isinstance(row, list) and len(row) == 6, 'changed RTWH row')
            if text(row[0]): added = text(row[0])
            if text(row[1]): office = {'House': 'house', 'Senate': 'senate', 'Governor': 'governor'}.get(text(row[1]))
            if not office: continue
            link = row[3]
            require(isinstance(link, dict) and link.get('type') == 'link', 'missing RTWH original link')
            source = safe_link(link['href']); location = text(row[2]); state = None; district = None
            if office == 'house':
                match = re.fullmatch(r'([A-Z]{2})\s*-\s*(\d{1,2}|AL)', location)
                if match and match[1] in state_names:
                    state = match[1]; district = '00' if match[2] == 'AL' else match[2].zfill(2)
            else:
                matches = [st for st, name in state_names.items() if location.startswith(name + ' - ')]
                if len(matches) == 1: state = matches[0]
            # Unknown display abbreviations remain unresolved, not guessed.
            rid = f'USA:{state}:{office}' + (f':{district}' if district else '') if state else None
            record = {'source': 'Race to the WH', 'source_url': source, 'aggregator_url': RTWH,
                'race_id': rid, 'state': state, 'office': office, 'district': district,
                'location_label': location, 'added_label': added, 'poll_label': text(link),
                'displayed_results': text(row[5]), 'displayed_leader': text(row[4]),
                'field_start': None, 'field_end': None, 'population': None, 'sample_n': None,
                'election_phase': 'unclassified', 'ballot_format': 'not_reviewed',
                'status': 'primary_review_required', 'signal_eligible': False,
                'linked_source_role': 'unverified_aggregator_link',
                'missing_fields': ['primary_question', 'fieldwork_dates', 'question_sample_n', 'population', 'commissioner'],
                'note_ko': '표의 등급·날짜·표본·후보 약칭은 원문 확인 전 참고이며 우리 정확도 등급·조사 승인으로 사용하지 않음.'}
            record['id'] = 'discovery-rtwh-' + digest(record)[:20]
            records.append(record)
        except (ValueError, TypeError, KeyError) as exc:
            skipped.append({'row': index, 'reason': str(exc)[:120]})
    require(records, 'no usable RTWH public poll links')
    return list({r['id']: r for r in records}.values()), skipped


def parse_rss(body, as_of):
    require(b'<!DOCTYPE' not in body.upper() and b'<!ENTITY' not in body.upper(), 'unsafe podcast XML')
    root = ET.fromstring(body); channel = root.find('channel')
    require(root.tag == 'rss' and channel is not None and channel.findtext('title') == 'Still Counting',
            'changed podcast identity')
    records = []
    for item in channel.findall('item')[:40]:
        published = parsedate_to_datetime(item.findtext('pubDate'))
        require(published.tzinfo is not None, 'undated podcast timezone')
        if published.date() > date.fromisoformat(as_of): continue
        link = safe_link(item.findtext('link'))
        require(urlparse(link).hostname == 'audioboom.com', 'unexpected episode host')
        guid = item.findtext('guid'); require(guid, 'missing podcast GUID')
        records.append({'id': 'commentary-still-counting-' + digest(guid)[:20],
            'title': item.findtext('title'), 'source': 'Still Counting', 'source_url': link,
            'published_at': published.isoformat(), 'kind': 'podcast_commentary',
            'status': 'discovery_only_not_transcribed', 'signal_eligible': False,
            'note_ko': '방송 발견 기록. 음성 전사·조사 수치 검증 전이며 여론조사 건수·우세 집계에 포함하지 않음.'})
    require(records, 'no dated podcast discovery entries')
    return records


def collect_additional(cycle, as_of, captured_at, state_names, opener=urlopen):
    health = {}; records = []; commentary = []
    publisher = fetch(RTWH, captured_at, health, 'rtwh_publisher', opener)
    if publisher is not None:
        try:
            require(EMBED in unescape(publisher.decode()), 'RTWH no longer publishes reviewed embed')
            embed = fetch(EMBED, captured_at, health, 'rtwh_embed', opener)
            if embed is not None:
                key = live_key(embed.decode())
                live = fetch(LIVE_BASE+key, captured_at, health, 'rtwh_table', opener)
                if live is not None:
                    records, skipped = parse_rtwh(json.loads(live), cycle, state_names)
                    health['rtwh_table'].update(status='partial' if skipped else 'ok',
                        record_count=len(records), skipped_rows=skipped, scope='published_latest_list_not_full_cycle')
        except (ValueError, KeyError, TypeError) as exc:
            health['rtwh_parse'] = {'status': 'unavailable', 'error_type': type(exc).__name__, 'attempted_at': captured_at}
    body = fetch(RSS, captured_at, health, 'still_counting', opener)
    if body is not None:
        try:
            commentary = parse_rss(body, as_of)
            health['still_counting'].update(status='ok', commentary_count=len(commentary))
        except (ValueError, KeyError, TypeError, ET.ParseError) as exc:
            health['still_counting'].update(status='unavailable', error_type=type(exc).__name__)
    return {'records': records, 'commentary': commentary, 'source_health': health}


def extend_report(report, additional):
    report['records'].extend(additional['records'])
    report['commentary'] = additional['commentary']
    report['source_health'].update(additional['source_health'])
    report['summary'] = {'discovered_records': len(report['records']),
        'races': len({r['race_id'] for r in report['records'] if r.get('race_id')}),
        'by_office': dict(Counter(r['office'] or 'unresolved' for r in report['records'])),
        'signal_eligible_records': 0, 'commentary_entries': len(report['commentary'])}
    report['status'] = 'partial' if report['status'] != 'ok' or any(
        r['status'] in ('partial', 'unavailable') for r in additional['source_health'].values()) else 'ok'
    return report
