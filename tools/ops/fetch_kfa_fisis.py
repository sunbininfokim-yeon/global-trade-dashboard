#!/usr/bin/env python3
"""Insurer CSM (보험계약마진) and IFRS 17 P&L by quarter from FSS FISIS.

Writes New for anti/public/data/kfa_fisis_insurance_v1.json for every insurer
that has an engine snapshot (kfa_pecr/index_v1.json, entity matched to the
FISIS company list by name):

    책임준비금 적립현황(23.3월 이후)  SH156 (생명) / SI152 (손해)
        A113 보험계약마진, A112 위험조정, A111 최선추정 (보험계약부채 잔여보장요소)
    손익발생원천별 실적(23.3월 이후)  SH155 / SI151
        A 보험손익, B 투자손익, C 영업이익, G 당기순이익

FISIS reports each insurer on its own (별도) books, so the figures differ from
the consolidated statements; the calculator says so. The API needs a free
registration key ($FISIS_API_KEY, GitHub secret) -- the one exception to the
key-free rule, agreed 2026-11-27. Exits 0 with the previous file kept when the
key is missing or FISIS is down.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'New for anti' / 'public' / 'data'
OUT = DATA / 'kfa_fisis_insurance_v1.json'
URL = 'https://fisis.fss.or.kr/openapi/{api}.json?lang=kr&auth={key}&{q}'
TABLES = {'H': ('SH156', 'SH155'), 'I': ('SI152', 'SI151')}       # (reserves, P&L) for life / non-life
RESERVE = {'A113': 'csm', 'A112': 'risk_adjustment', 'A111': 'best_estimate', 'A1': 'insurance_liabilities'}
PNL = {'A': 'insurance_result', 'A1': 'insurance_revenue', 'B': 'investment_result', 'C': 'operating_income', 'G': 'net_income'}


def call(api: str, q: str) -> dict:
    key = os.environ['FISIS_API_KEY'].strip()
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(URL.format(api=api, key=key, q=q), headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=90) as r:
                res = json.loads(r.read().decode('utf-8'))['result']
            if res.get('err_cd') not in ('000', None):
                raise RuntimeError(f"{api}: {res.get('err_cd')} {res.get('err_msg')}")
            return res
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 -- FISIS is slow; retried
            last = exc
            time.sleep(3 * (i + 1))
    raise RuntimeError(f'{api} failed: {str(last)[:80]}')


def norm(name: str) -> str:
    return re.sub(r'\(주\)|㈜|주식회사|\[폐\]|\s', '', name or '')


def series(cd: str, list_no: str, accounts: dict, start: str, end: str) -> dict:
    rows = call('statisticsInfoSearch', f'financeCd={cd}&listNo={list_no}&term=Q&startBaseMm={start}&endBaseMm={end}').get('list') or []
    out = {}
    for r in rows:
        k = accounts.get(r.get('account_cd'))
        if not k:
            continue
        try:
            v = float(str(r.get('a')).replace(',', ''))
        except ValueError:
            continue
        out.setdefault(r['base_month'], {})[k] = v
    return out


def main() -> int:
    if not os.environ.get('FISIS_API_KEY', '').strip():
        print('FISIS_API_KEY not set -- keeping the previous file', file=sys.stderr)
        return 0
    index = json.loads((DATA / 'kfa_pecr' / 'index_v1.json').read_text()).get('index') or {}
    today = dt.date.today()
    start, end = f'{today.year - 3}01', f'{today.year}12'
    companies = {}
    try:
        for part in TABLES:
            for c in call('companySearch', f'partDiv={part}').get('list') or []:
                if '[폐]' not in (c.get('finance_nm') or ''):
                    companies[norm(c['finance_nm'])] = (part, c['finance_cd'], c['finance_nm'])
    except Exception as exc:  # noqa: BLE001
        print(f'FISIS unavailable ({exc}) -- keeping the previous file', file=sys.stderr)
        return 0
    prev = json.loads(OUT.read_text()).get('insurers', {}) if OUT.exists() else {}
    insurers, missed = {}, []
    for corp, meta in index.items():
        if not meta.get('financial') or meta.get('market') == 'US':
            continue
        hit = companies.get(norm(meta.get('entity')))
        if not hit:
            continue
        part, cd, fname = hit
        try:
            res, pnl = TABLES[part]
            q = series(cd, res, RESERVE, start, end)
            for ym, v in series(cd, pnl, PNL, start, end).items():
                q.setdefault(ym, {}).update(v)
        except Exception as exc:  # noqa: BLE001 -- keep the previous entry
            missed.append(corp)
            print(f'FAILED {meta.get("entity")}: {exc}', file=sys.stderr)
            if corp in prev:
                insurers[corp] = {**prev[corp], 'stale': True}
            continue
        if q:
            insurers[corp] = {'entity': meta.get('entity'), 'finance_cd': cd, 'fisis_name': fname,
                              'kind': '생명보험' if part == 'H' else '손해보험', 'quarters': dict(sorted(q.items()))}
            last = max(q)
            print(f'{fname}: {len(q)} quarters, CSM {q[last].get("csm")} ({last})')
    doc = {'schema': 'kfa_fisis_insurance/1', 'generated_at': dt.datetime.now().isoformat(timespec='seconds'),
           'source': 'FSS FISIS 금융통계정보시스템 (책임준비금 적립현황·손익발생원천별 실적, 23.3월 이후)',
           'basis': '개별 회사(별도) 기준, 원 단위, 분기말', 'insurers': insurers}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
    print(f'wrote {OUT.relative_to(ROOT)}: {len(insurers)} insurers, {len(missed)} failed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
