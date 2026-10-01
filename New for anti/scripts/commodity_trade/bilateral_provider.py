"""Bounded source acquisition. Direct and protected-gateway modes share parsers.

One job = one reporter/HS/period/direction and explicit partner scope.
No implicit fallback to annual data; no credentials or raw error bodies persisted.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from xml.etree import ElementTree as ET

from bilateral import ContractError, number, partner_code
from country_codes import ISO2_TO_ISO3
from priority_universe import PRIORITY_REPORTERS

LIMIT = 500
MAX_BYTES = 4 * 1024 * 1024
KOREA_PARTNERS = {str(int(meta['m49'])): iso2 for iso2, iso3 in ISO2_TO_ISO3.items()
                  if (meta := PRIORITY_REPORTERS.get(iso3))}
CT_QUALITY = ('isReported', 'isAggregate', 'isNetWgtEstimated', 'isQtyEstimated',
              'isAltQtyEstimated', 'isOriginalClassification', 'legacyEstimationFlag',
              'qty', 'qtyUnitCode', 'qtyUnitAbbr', 'altQty', 'altQtyUnitCode',
              'classificationCode', 'partnerISO', 'partnerDesc')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward credentials to a redirect destination.


def read_http(url, *, headers=None, data=None, timeout=30):
    with build_opener(NoRedirect()).open(Request(url, headers=headers or {}, data=data), timeout=timeout) as r:
        body = r.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ContractError('response_size_limit')
        return body


def query_for(job):
    m = job['meta']
    if len(m['requested_flows']) != 1:
        raise ContractError('source jobs require one direction')
    q = dict(query_id=job['id'], source=m['source'], reporter=m['reporter'],
             hs=m['hs'], period=m['period'], frequency=m['frequency'],
             flow=m['requested_flows'][0], partners=job['partners'])
    if m['source'] == 'korea_customs':
        if m['reporter'] != '410' or m['frequency'] != 'M' or len(job['partners']) != 1:
            raise ContractError('Korea requires one monthly partner per query')
        p = job['partners'][0]
        if p != '0' and p not in KOREA_PARTNERS:
            raise ContractError('Korea partner ISO2 mapping unavailable')
        q['partner_iso2'] = None if p == '0' else KOREA_PARTNERS[p]
    elif m['source'] != 'comtrade':
        raise ContractError('unsupported source')
    return q


def source_request(q, *, preview=False):
    if q['source'] == 'comtrade':
        base = 'https://comtradeapi.un.org/' + ('public/v1/preview' if preview else 'data/v1/get')
        params = dict(reporterCode=q['reporter'], period=q['period'], cmdCode=q['hs'],
                      flowCode=q['flow'], partnerCode='' if q['partners'] == ['*'] else ','.join(q['partners']),
                      partner2Code='0', customsCode='C00', motCode='0', maxRecords=LIMIT)
        return f"{base}/C/{q['frequency']}/HS?{urlencode(params)}", {'Accept': 'application/json'}
    op = 'nitemtrade/getNitemtradeList' if q.get('partner_iso2') else 'Itemtrade/getItemtradeList'
    params = dict(strtYymm=q['period'], endYymm=q['period'], hsSgn=q['hs'])
    if q.get('partner_iso2'):
        params['cntyCd'] = q['partner_iso2']
    return 'https://apis.data.go.kr/1220000/' + op + '?' + urlencode(params), {'Accept': 'application/xml'}


def normalize_comtrade(body, job):
    m = job['meta']
    rows = body.get('data')
    if not isinstance(rows, list) or body.get('count') != len(rows):
        raise ContractError('invalid Comtrade count/data')
    result = []
    for r in rows:
        if (str(r.get('reporterCode')) != m['reporter'] or str(r.get('period')) != m['period']
                or r.get('cmdCode') != m['hs'] or r.get('freqCode') != m['frequency']
                or r.get('classificationCode') != m['hs_version']
                or r.get('flowCode') not in m['requested_flows']
                or str(r.get('partner2Code')) != '0' or r.get('customsCode') != 'C00'
                or str(r.get('motCode')) != '0'):
            raise ContractError('Comtrade statistical scope mismatch')
        # Explicit source FOB/CIF only; primaryValue retained as provenance when
        # the valuation basis cannot be verified. Never infer volume from money.
        value_field = 'fobvalue' if r['flowCode'] == 'X' else 'cifvalue'
        quality = {k: r.get(k) for k in CT_QUALITY}
        quality['primary_value_usd'] = number(r.get('primaryValue'))
        quality['value_field'] = value_field
        result.append(dict(partner=partner_code(r.get('partnerCode')), flow=r['flowCode'], period=m['period'],
                           metrics={'net_weight_kg': number(r.get('netWgt')),
                                    'trade_value_usd': number(r.get(value_field))}, quality=quality))
    return result, len(rows) < LIMIT and body.get('mayBeTruncated') is not True


def normalize_korea(document, job):
    if b'<!DOCTYPE' in document.upper() or b'<!ENTITY' in document.upper():
        raise ContractError('XML entities prohibited')
    root = ET.fromstring(document)
    if root.findtext('./header/resultCode') != '00':
        raise ContractError('Korea service error')
    m, partner = job['meta'], job['partners'][0]
    wanted = m['period'][:4] + '.' + m['period'][4:]
    rows = []
    items = root.findall('./body/items/item')
    total = root.findtext('./body/totalCount')
    complete = total is None or (total.isdigit() and int(total) == len(items))
    matched_count = 0
    for item in items:
        if item.findtext('year') in {'총계', '합계'}:
            continue
        code = item.findtext('hsCd') if partner != '0' else item.findtext('hsCode')
        if item.findtext('year') != wanted or code != m['hs']:
            raise ContractError('Korea month/HS mismatch')
        matched_count += 1
        if partner != '0' and item.findtext('statCd') != KOREA_PARTNERS[partner]:
            raise ContractError('Korea returned partner mismatch')
        for flow in m['requested_flows']:
            prefix = 'exp' if flow == 'X' else 'imp'
            def val(field):
                v = item.findtext(prefix + field)
                return number(v.strip().replace(',', '') if v else None)
            rows.append(dict(partner=partner, flow=flow, period=m['period'],
                             metrics={'net_weight_kg': val('Wgt'), 'trade_value_usd': val('Dlr')},
                             quality={'mass_basis': 'net_weight_kg', 'value_basis': 'FOB' if flow == 'X' else 'CIF',
                                      'reported_partner_iso2': item.findtext('statCd'), 'isNetWgtEstimated': None}))
    return rows, complete and matched_count == 1


class Provider:
    def __init__(self, mode='preview', *, interval=3, http=read_http):
        if mode not in {'preview', 'direct', 'gateway'}:
            raise ContractError('unknown acquisition mode')
        self.mode, self.interval, self.http, self.last_call = mode, max(0, interval), http, 0.0
        self.calls = 0

    def __call__(self, job):
        out = {'query_id': job['id'], 'status': 'error', 'response_complete': False, 'rows': []}
        q = query_for(job)
        try:
            url, headers = source_request(q, preview=self.mode == 'preview')
            data = None
            if self.mode == 'gateway':
                url = os.getenv('TRADE_GATEWAY_URL', '')
                u = urlsplit(url)
                if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment:
                    raise ContractError('invalid gateway URL')
                key = os.getenv('TRADE_PIPELINE_TOKEN')
                if not key:
                    return dict(out, status='auth_required')
                headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
                data = json.dumps(q).encode()
            elif q['source'] == 'korea_customs':
                key = os.getenv('KOREA_CUSTOMS_SERVICE_KEY')
                if not key:
                    return dict(out, status='auth_required')
                url += '&' + urlencode({'serviceKey': unquote(key)})
            elif self.mode == 'direct':
                key = os.getenv('COMTRADE_API_KEY') or os.getenv('COMTRADE_SUBSCRIPTION_KEY')
                if not key:
                    return dict(out, status='auth_required')
                headers['Ocp-Apim-Subscription-Key'] = key
            wait = self.interval - (time.monotonic() - self.last_call)
            if wait > 0:
                time.sleep(wait)
            self.last_call = time.monotonic()
            self.calls += 1
            body = self.http(url, headers=headers, data=data)
            if self.mode == 'gateway':
                envelope = json.loads(body)
                if envelope.get('query_id') != job['id']:
                    raise ContractError('gateway identity mismatch')
                if envelope.get('status') != 'ok':
                    return dict(out, status=envelope.get('status', 'error'))
                body = envelope['payload'].encode()
            if q['source'] == 'korea_customs':
                if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
                    raise ContractError('XML entities prohibited')
                code = ET.fromstring(body).findtext('./header/resultCode')
                if code in {'20', '30', '31', '32'}:
                    return dict(out, status='auth_required')
                if code in {'22', '23'}:
                    return dict(out, status='rate_limited')
            rows, complete = (normalize_comtrade(json.loads(body), job) if q['source'] == 'comtrade'
                              else normalize_korea(body, job))
            return dict(out, status='ok' if rows else 'empty', rows=rows, response_complete=complete,
                        retrieved_at=datetime.now(timezone.utc).isoformat())
        except HTTPError as e:
            return dict(out, status='rate_limited' if e.code == 429 else 'auth_required' if e.code in {401, 403} else 'error')
        except URLError:
            return dict(out, status='network_error')  # Stop this run; do not burn the entire plan on DNS failure.
        except (OSError, ValueError, ET.ParseError, KeyError, TypeError):
            return out  # Never expose URLs, bodies, headers, or exception text.
