#!/usr/bin/env python3
"""Run Codex's PE/CR engine on live OpenDART filings and publish the results.

The engine (New for anti/scripts/dart/build_pe_cr.py, dart_kfa/pe_cr*.py) is
offline-only: it takes saved OpenDART responses and returns `pe_cr` cards.
Its own handoff (docs/PE_CR_ENGINE.md, "사용과 Claude 인수인계") says the
Worker must not re-implement the formulas but serve the engine's output.
This script is that bridge for now: fetch -> engine -> static JSON under
New for anti/public/data/kfa_pecr/<corp_code>_v1.json, which the calculator
reads alongside the live /api/dart-financials response.

Per company it fetches (key from the environment only, never written):
  company.json                    induty_code -> engine's industry kit
  fnlttSinglAcntAll FY/Q1/H1/Q3   latest fiscal year, CFS or OFS (one basis)
  fnlttSinglAcntAll FY            two prior years, for opening balances
  cprndNrdmpBlce / entrprsBilScritsNrdmpBlce / srtpdPsndbtNrdmpBlce
                                  회사채 / CP / 단기사채 미상환 잔액 (FY report)

The 미상환 잔액 responses carry no unit. The engine's tests assume 백만원,
which is the usual layout but not guaranteed, so the unit is chosen by
cross-checking the corporate-bond total against the balance-sheet bond
balance (BS ifrs-full_BondsIssued / dart_Bonds...). If no scale lands within
a 3x band, funding is left out for that company rather than guessed.

Raw responses are cached under --cache (default: a scratch dir) so a rerun
does not spend API quota; nothing raw is published.

Usage:
    DART_API_KEY=... python3 tools/ops/build_kfa_pecr_snapshots.py [corp_code ...]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'New for anti' / 'scripts' / 'dart'
OUT_DIR = ROOT / 'New for anti' / 'public' / 'data' / 'kfa_pecr'
API = 'https://opendart.fss.or.kr/api'
PAUSE = 0.15

# Validation set named in docs/PE_CR_ENGINE.md "배포 전 필수": 제조, 반도체,
# 조선/건설, 해운, 금융 -- plus 유통·IT·방산 and the unlisted filers the user
# asked about. (corp_code, KRX code or None, label for logs)
DEFAULT_TARGETS = [
    ('00126380', '005930', '삼성전자'),        # 제조/전자
    ('00164779', '000660', 'SK하이닉스'),      # 반도체
    ('00164830', '009540', 'HD한국조선해양'),  # 조선
    ('00111704', '042660', '한화오션'),        # 조선
    ('00126478', '010140', '삼성중공업'),      # 조선
    ('00164478', '000720', '현대건설'),        # 건설
    ('00120438', None, '롯데건설'),            # 건설, 비상장
    ('00164645', '011200', 'HMM'),             # 해운
    ('00122737', '028670', '팬오션'),          # 해운
    ('00872984', '139480', '이마트'),          # 유통
    ('00266961', '035420', 'NAVER'),           # IT
    ('00159616', '034020', '두산에너빌리티'),  # 기계
    ('00819268', None, '연합자산관리'),        # 금융: NPL
    ('00416593', None, '대신에프앤아이'),      # 금융: NPL
    ('00688996', '105560', 'KB금융'),          # 금융: 은행지주 (Basel)
    ('00382199', '055550', '신한지주'),        # 금융: 은행지주 (Basel)
    ('00168933', None, 'DB생명보험'),          # 보험 (K-ICS), 비상장
    ('00126256', '032830', '삼성생명'),        # 보험 (K-ICS)
    ('00159102', '005830', 'DB손해보험'),      # 보험 (K-ICS)
    ('00296290', '039490', '키움증권'),        # 증권 (NCR)
    ('00222374', None, '현대카드'),            # 카드 (조정자기자본비율), 비상장
    ('00208514', None, '현대캐피탈'),          # 캐피탈 (조정자기자본비율), 비상장
]

FUNDING_ENDPOINTS = {
    'corporate_bond': 'cprndNrdmpBlce',
    'commercial_paper': 'entrprsBilScritsNrdmpBlce',
    'short_term_bond': 'srtpdPsndbtNrdmpBlce',
}
FUNDING_LABEL = {'corporate_bond': '회사채', 'commercial_paper': '기업어음(CP)', 'short_term_bond': '단기사채'}
REPRT = {'FY': '11011', 'Q1': '11013', 'H1': '11012', 'Q3': '11014'}


class BudgetExhausted(RuntimeError):
    """OpenDART daily quota (20,000 calls per key) or this run's --max-calls."""


class Dart:
    def __init__(self, key: str, cache: Path, max_calls: int | None = None):
        import threading
        self.key, self.cache, self.max_calls, self.calls = key, cache, max_calls, 0
        self._lock = threading.Lock()
        cache.mkdir(parents=True, exist_ok=True)

    def _spend(self):
        with self._lock:
            if self.max_calls is not None and self.calls >= self.max_calls:
                raise BudgetExhausted(f'--max-calls {self.max_calls} reached')
            self.calls += 1

    def get_bytes(self, path: str, **params) -> bytes | None:
        """Binary endpoint (fnlttXbrl.xml zip), cached; None on an API error body."""
        name = path.replace('.xml', '') + '_' + '_'.join(f'{k}={v}' for k, v in sorted(params.items())) + '.bin'
        hit = self.cache / name
        if hit.exists():
            data = hit.read_bytes()
            return data or None
        q = urllib.parse.urlencode({'crtfc_key': self.key, **params})
        for attempt in range(3):
            self._spend()
            try:
                req = urllib.request.Request(f'{API}/{path}?{q}', headers={'User-Agent': 'global-trade-dashboard/1.0'})
                with urllib.request.urlopen(req, timeout=90) as res:
                    data = res.read()
            except Exception as exc:
                print(f'  retry {path}: {str(exc).replace(self.key, "<key>")}', file=sys.stderr)
                time.sleep(3 * (attempt + 1))
                continue
            time.sleep(PAUSE)
            ok = data[:2] == b'PK'           # a zip; errors come back as a small XML/JSON body
            hit.write_bytes(data if ok else b'')
            return data if ok else None
        return None

    def get(self, path: str, **params) -> dict:
        name = path.replace('.json', '') + '_' + '_'.join(f'{k}={v}' for k, v in sorted(params.items())) + '.json'
        hit = self.cache / name
        if hit.exists():
            return json.loads(hit.read_text())
        q = urllib.parse.urlencode({'crtfc_key': self.key, **params})
        for attempt in range(4):
            self._spend()
            try:
                req = urllib.request.Request(f'{API}/{path}?{q}', headers={'User-Agent': 'global-trade-dashboard/1.0'})
                with urllib.request.urlopen(req, timeout=40) as res:
                    data = json.loads(res.read())
            except Exception as exc:
                print(f'  retry {path}: {str(exc).replace(self.key, "<key>")}', file=sys.stderr)
                time.sleep(2 * (attempt + 1))
                continue
            if data.get('status') == '020':
                if attempt >= 1:
                    raise BudgetExhausted('OpenDART 020: daily request limit')
                time.sleep(5 * (attempt + 1))
                continue
            time.sleep(PAUSE)
            if data.get('status') in ('000', '013'):
                hit.write_text(json.dumps(data, ensure_ascii=False))
            return data
        raise RuntimeError(f'{path} {params} failed')


def report(dart: Dart, corp: str, year: int, bucket: str, fs_div: str) -> dict:
    resp = dart.get('fnlttSinglAcntAll.json', corp_code=corp, bsns_year=str(year), reprt_code=REPRT[bucket], fs_div=fs_div)
    return {'request': {'corp_code': corp, 'bsns_year': str(year), 'reprt_code': REPRT[bucket], 'fs_div': fs_div},
            'response': {'status': resp.get('status'), 'list': resp.get('list', [])}}


def pick_basis(dart: Dart, corp: str, today: dt.date) -> tuple[int, str]:
    """Latest fiscal year with an annual report, and the one CFS/OFS basis."""
    for year in (today.year - 1, today.year - 2):
        for fs in ('CFS', 'OFS'):
            if report(dart, corp, year, 'FY', fs)['response']['status'] == '000':
                return year, fs
    raise RuntimeError('no annual report in the last two years')


def num(v) -> float | None:
    s = str(v or '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


BOND_IDS = ('ifrs-full_BondsIssued', 'dart_BondsIssued', 'dart_ShortTermBonds', 'dart_LongTermBonds',
            'ifrs-full_CurrentPortionOfBondsIssued', 'dart_CurrentPortionOfBonds',
            'ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued', 'ifrs-full_CurrentPortionOfNoncurrentBondsIssued')
# Where a filer carries its bonds instead -- 연합자산관리 designates them at
# FVTPL (6.14조 FVTPL liabilities vs 3.5조 회사채 + 1.64조 CP + 0.25조 단기사채).
# SK하이닉스·이마트 fold bonds into 차입금 lines with no separate 사채 row.
DEBT_FALLBACK_IDS = ('ifrs-full_FinancialLiabilitiesAtFairValueThroughProfitOrLoss', 'ifrs-full_Borrowings',
                     'ifrs-full_OtherBorrowings', 'ifrs-full_ShorttermBorrowings', 'ifrs-full_LongtermBorrowings',
                     'ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings',
                     'ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived')


def bs_bonds(fy_rows: list) -> tuple[float | None, str]:
    """Balance-sheet comparator for the unit cross-check, and what it was."""
    def total(ids, by_name=False):
        acc, seen = 0.0, False
        for r in fy_rows:
            if r.get('sj_div') != 'BS':
                continue
            aid, nm = r.get('account_id', ''), (r.get('account_nm') or '').strip()
            if aid in ids or (by_name and re.fullmatch(r'(유동성)?사채', nm)):
                v = num(r.get('thstrm_amount'))
                if v:
                    acc += abs(v)
                    seen = True
        return acc if seen else None
    bonds = total(BOND_IDS, by_name=True)
    if bonds:
        return bonds, 'BS 사채'
    other = total(DEBT_FALLBACK_IDS)
    if other:
        return other, 'BS 차입성 부채 합계(사채 별도 계정 없음)'
    # Last resort (HD한국조선해양, 롯데건설 file borrowings under extension
    # tags): bonds cannot exceed total liabilities.
    liab = total(('ifrs-full_Liabilities',))
    return (liab, 'BS 부채총계(차입 계정 미표준)') if liab else (None, '')


def total_row(rows: list) -> dict | None:
    # Live responses label it "미상환잔액" (no space); the engine's default
    # selector and its fixtures use "미상환 잔액". Match either, then pass the
    # label actually seen as row_selector.
    hits = [r for r in rows if (r.get('remndr_exprtn1') or '').replace(' ', '') == '미상환잔액'
            and (r.get('remndr_exprtn2') or '').strip() == '합계']
    return hits[0] if len(hits) == 1 else None


def funding_packet(dart: Dart, corp: str, year: int, fy_rows: list, fs: str) -> tuple[dict | None, str]:
    raw = {k: dart.get(f'{ep}.json', corp_code=corp, bsns_year=str(year), reprt_code=REPRT['FY'])
           for k, ep in FUNDING_ENDPOINTS.items()}
    if all(r.get('status') != '000' for r in raw.values()):
        return None, 'no_instrument_disclosure'
    bond = total_row(raw['corporate_bond'].get('list', [])) if raw['corporate_bond'].get('status') == '000' else None
    bs, bs_basis = bs_bonds(fy_rows)
    scale = None
    if bond and bs:
        sm = num(bond.get('sm'))
        if sm:
            # Candidate units are 1000x apart, so a loose band picks exactly
            # one. Upper 3x, not 1x: the BS 사채 tag often holds only the
            # non-current part (현대건설 1.54조 outstanding vs 1.15조 tagged,
            # 삼성전자 143억 vs 71억), the current portion sitting in a
            # combined 유동성장기부채 line. Lower 0.001 for filers whose
            # comparator is a much wider total.
            fits = [s for s in (1, 1_000, 1_000_000) if 0.001 <= (sm * s) / bs <= 3]
            if fits:
                scale = max(fits)
    if scale is None:
        return None, 'unit_not_cross_checked:' + ('no_bs_debt' if not bs else 'no_bond_total' if not bond else 'out_of_band')
    packets = {}
    as_of, receipt = None, None
    for k, r in raw.items():
        if r.get('status') != '000' or not r.get('list'):
            continue
        tot = total_row(r['list'])
        if tot is None:
            continue
        row0 = tot
        as_of = as_of or row0.get('stlm_dt')
        receipt = receipt or row0.get('rcept_no')
        packets[k] = {
            'endpoint': FUNDING_ENDPOINTS[k], 'as_of': row0.get('stlm_dt'), 'receipt': row0.get('rcept_no'),
            'scope': 'issuer_only', 'currency': 'KRW', 'scale': scale,
            'scope_evidence': f'OpenDART {FUNDING_ENDPOINTS[k]} / {FUNDING_LABEL[k]} 미상환잔액 / 합계; '
                              f'단위는 회사채 합계({num(bond.get("sm")):,.0f})를 {bs_basis}({bs:,.0f})와 대조해 {scale:,}원으로 판정(자동)',
            'row_selector': {'remndr_exprtn1': tot.get('remndr_exprtn1'), 'remndr_exprtn2': '합계'},
            # "-" in a bucket of a table whose 합계 is a number is an empty
            # bucket; a "-" 합계 is left unconfirmed (engine -> unavailable).
            'dash_means_zero': num(tot.get('sm')) is not None,
            'response': {'status': r['status'], 'list': r['list']},
        }
    if not packets:
        return None, 'no_instrument_rows'
    return ({'schema_version': 'kfa-funding-disclosure/1', 'entity_id': corp, 'as_of': as_of,
             'fs_div': fs, 'currency': 'KRW', 'scale': 1, 'dart_instruments': packets},
            f'scale={scale}')


def yahoo_close(code: str, day: str, cache: Path) -> float | None:
    """Close on exactly `day` (KST trading date) for code.KS / code.KQ."""
    hit = cache / f'yahoo_{code}_{day}.json'
    if hit.exists():
        return json.loads(hit.read_text()).get('close')
    d = dt.date.fromisoformat(day)
    p1 = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp()) - 86400
    close = None
    for suffix in ('.KS', '.KQ'):
        url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{code}{suffix}'
               f'?period1={p1}&period2={p1 + 3 * 86400}&interval=1d')
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as res:
                result = (json.loads(res.read()).get('chart') or {}).get('result') or []
        except Exception:
            continue
        if not result:
            continue
        stamps = result[0].get('timestamp') or []
        closes = ((result[0].get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
        kst = dt.timezone(dt.timedelta(hours=9))
        for t, c in zip(stamps, closes):
            if c and dt.datetime.fromtimestamp(t, kst).date().isoformat() == day:
                close = float(c)
        if close:
            break
        time.sleep(0.3)
    hit.write_text(json.dumps({'close': close}))
    return close


COMMON_LABELS = {'보통주', '보통주식'}
NON_CLASS_LABELS = {'합계', '총계', '계', '비고'}


def _se(r) -> str:
    return (r.get('se') or '').replace(' ', '')


def share_rows(dart: Dart, corp: str, today: dt.date) -> tuple[list, str | None]:
    """Newest stockTotqySttus that actually carries a common-share row.

    Some Q3 filings come back with only 합계 "-" / 비고 (한화오션, 팬오션
    FY2026 Q3), so walk back until one has the table."""
    for year, code in ((today.year, '11014'), (today.year, '11012'), (today.year, '11013'), (today.year - 1, '11011')):
        r = dart.get('stockTotqySttus.json', corp_code=corp, bsns_year=str(year), reprt_code=code)
        rows = r.get('list') or []
        if r.get('status') == '000' and any(_se(x) in COMMON_LABELS and num(x.get('distb_stock_co')) for x in rows):
            return rows, rows[0].get('rcept_no')
    return [], None


def market_packet(dart: Dart, corp: str, stock: str, fy_receipt: str, today: dt.date) -> tuple[dict | None, str]:
    """Point-in-time market input in the engine's `market` contract.

    The share count and the price are taken on the *same* day -- the latest
    periodic report's settlement date -- so the engine's 120-day /
    corporate-action rule is met by construction rather than by asserting a
    check nobody ran. The quote is therefore up to one quarter old; its date
    travels with the card (market_date).
    """
    rows, receipt = share_rows(dart, corp, today)
    if not rows:
        return None, 'no_share_count_report'
    commons = [r for r in rows if _se(r) in COMMON_LABELS]
    if len(commons) != 1:
        return None, 'no_single_common_share_row'
    common = commons[0]
    # Every other share class (우선주, 종류주식 ...) with outstanding shares.
    others = [r for r in rows if _se(r) not in COMMON_LABELS | NON_CLASS_LABELS and num(r.get('distb_stock_co'))]
    as_of = common.get('stlm_dt')
    shares = num(common.get('distb_stock_co'))
    if not as_of or not shares:
        return None, 'common_share_count_missing'
    price = yahoo_close(stock, as_of, dart.cache)
    if not price:
        return None, f'no_close_on_{as_of}'
    src = f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}'
    cls = {'id': f'{stock}:common', 'price': price, 'price_date': as_of, 'price_source': 'Yahoo Finance chart API daily close',
           'shares_out': int(shares), 'shares_date': as_of, 'shares_source': src, 'currency': 'KRW',
           'share_basis': 'outstanding_excluding_treasury'}
    market = {'is_listed': True, 'entity_id': corp, 'currency': 'KRW', 'as_of': as_of,
              'fundamentals_available_date': f'{fy_receipt[:4]}-{fy_receipt[4:6]}-{fy_receipt[6:8]}',
              'coverage': 'all_ordinary_share_classes', 'classes': [cls]}
    note = f'as_of={as_of} common={int(shares)}@{price:,.0f}'
    if not others:
        # 주식의 총수 현황 shows no other class outstanding (absent, "-" or 0).
        market['preferred_equity'] = {'value': 0, 'as_of': as_of, 'currency': 'KRW', 'source': src,
                                      'basis': 'verified_no_preferred_outstanding'}
    elif len(others) > 1 or _se(others[0]) != '우선주':
        note += ' other_share_classes_unpriced'   # 종류주식 etc.: leave EV unavailable
    else:
        pref_shares = num(others[0].get('distb_stock_co'))
        pcode = stock[:-1] + '5'   # KRX convention for the first preferred line (005930 -> 005935)
        pprice = yahoo_close(pcode, as_of, dart.cache)
        if pprice:
            market['preferred_coverage'] = 'all_preferred_share_classes'
            market['preferred_classes'] = [{**cls, 'id': f'{pcode}:preferred', 'price': pprice, 'shares_out': int(pref_shares)}]
            note += f' preferred={int(pref_shares)}@{pprice:,.0f}'
        else:
            note += ' preferred_unpriced'
    return market, note


# --- Valuation denominators ----------------------------------------------------
# The market multiples are 시가총액 ÷ 분모. The engine snapshot keeps the
# denominators; tools/ops/fetch_kfa_market.py keeps the daily 시가총액; the
# calculator divides. Flows come as FY and as LTM (trailing four quarters from
# the newest later report: FY + 당기 누적 − 전기 동기 누적, all three from
# filings of the same basis); balances as of the newest report.
VB_FLOWS = {
    'net_income_parent': ['ifrs-full_ProfitLossAttributableToOwnersOfParent'],
    'net_income': ['ifrs-full_ProfitLoss'],
    'revenue': ['ifrs-full_Revenue'],
    'operating_income': ['dart_OperatingIncomeLoss'],
}
VB_BALANCES = {
    'parent_equity': ['ifrs-full_EquityAttributableToOwnersOfParent'],
    'equity': ['ifrs-full_Equity'],
}


def _vb_row(rows: list, ids: list, sjs: tuple) -> dict | None:
    for sj in sjs:
        for r in rows:
            if r.get('sj_div') == sj and r.get('account_id') in ids:
                return r
    return None


def valuation_bases(dart: Dart, corp: str, year: int, fs: str, fy_rows: list, cards: dict) -> dict:
    out = {'fy': {'period_end': f'{year}-12-31', 'receipt': fy_rows[0].get('rcept_no') if fy_rows else None}}
    for key, ids in VB_FLOWS.items():
        r = _vb_row(fy_rows, ids, ('IS', 'CIS'))
        out['fy'][key] = num(r.get('thstrm_amount')) if r else None
    for key, ids in VB_BALANCES.items():
        r = _vb_row(fy_rows, ids, ('BS',))
        out['fy'][key] = num(r.get('thstrm_amount')) if r else None
    # Engine cards that already are FY denominators (strict first, else reported basis).
    def card(*keys):
        for k in keys:
            v = (cards.get(k) or {}).get('value')
            if v is not None:
                return v, k
        return None, None
    for name, keys in {'ebitda': ('ebitda', 'ebitda_cf'), 'net_debt': ('net_debt', 'net_debt_reported'),
                       'fcf': ('fcf',), 'cfo': ('cfo',)}.items():
        v, k = card(*keys)
        out['fy'][name] = v
        out['fy'][name + '_card'] = k
    # LTM from the newest later report.
    for bucket, label in (('Q3', '09-30'), ('H1', '06-30'), ('Q1', '03-31')):
        r = report(dart, corp, year + 1, bucket, fs)
        rows = r['response']['list'] if r['response']['status'] == '000' else []
        if not rows:
            continue
        ltm = {'period_end': f'{year + 1}-{label}', 'report': bucket, 'receipt': rows[0].get('rcept_no')}
        for key, ids in VB_FLOWS.items():
            row = _vb_row(rows, ids, ('IS', 'CIS'))
            fy = out['fy'].get(key)
            cur = num(row.get('thstrm_add_amount') or row.get('thstrm_amount')) if row else None
            prior = num(row.get('frmtrm_add_amount') or row.get('frmtrm_q_amount')) if row else None
            ltm[key] = fy + cur - prior if None not in (fy, cur, prior) else None
        for key, ids in VB_BALANCES.items():
            row = _vb_row(rows, ids, ('BS',))
            ltm[key] = num(row.get('thstrm_amount')) if row else None
        if any(ltm.get(k) is not None for k in VB_FLOWS):
            out['ltm'] = ltm
            break
    return out


REPORT_NAME = re.compile(r'(사업보고서|반기보고서|분기보고서)\s*\((\d{4})\.(\d{2})\)')
REPORT_KIND = {('사업보고서', '12'): 'FY', ('반기보고서', '06'): 'H1', ('분기보고서', '03'): 'Q1', ('분기보고서', '09'): 'Q3'}
MONTH_END = {'03': '03-31', '06': '06-30', '09': '09-30', '12': '12-31'}


def periodic_reports(dart: Dart, corp: str, year: int) -> list[dict]:
    """The FY `year` 사업보고서 and every later 분기/반기보고서, newest first.
    `receipts` lists every filing of that report, newest first: a [기재정정]
    filing may carry only the corrected sections (KB금융 FY2025's 2026-06
    correction has no BIS table), so callers fall back to older receipts."""
    lst = dart.get('list.json', corp_code=corp, bgn_de=f'{year + 1}0101', pblntf_ty='A', page_count=100)
    best = {}
    for row in lst.get('list') or []:
        m = REPORT_NAME.search(row.get('report_nm') or '')
        if not m:
            continue
        kind = REPORT_KIND.get((m.group(1), m.group(3)))
        period_end = f'{m.group(2)}-{MONTH_END[m.group(3)]}'
        if not kind or (kind == 'FY' and int(m.group(2)) != year) or period_end < f'{year}-12-31':
            continue
        key = (kind, period_end)
        best.setdefault(key, {'kind': kind, 'period_end': period_end, 'receipts': []})['receipts'].append(row['rcept_no'])
    for r in best.values():
        r['receipts'].sort(reverse=True)
    return sorted(best.values(), key=lambda r: r['period_end'], reverse=True)


def report_body(dart: Dart, receipt: str) -> str | None:
    blob = dart.get_bytes('document.xml', rcept_no=receipt)
    if not blob:
        return None
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = f'{receipt}.xml'
        if name not in z.namelist():
            return None
        return z.read(name).decode('utf-8', errors='ignore')


def regulatory_series(dart: Dart, corp: str, year: int, company: dict, fs: str):
    """K-ICS / Basel / NCR / 조정자기자본비율 from the report bodies."""
    from dart_kfa.entity_policy import classify_entity  # noqa: E402
    from dart_kfa.regulatory_capital import regulatory_from_reports, regulatory_kind  # noqa: E402
    name = company.get('corp_name') or ''
    policy = classify_entity({'corp_code': corp, 'induty_code': company.get('induty_code'), 'corp_name': name})
    kind, subtype = regulatory_kind(policy.get('entity_class'), name)
    if not kind:
        return None, 'not_regulated_capital_filer'
    from dart_kfa.regulatory_capital import extract  # noqa: E402
    reports = []
    for r in periodic_reports(dart, corp, year):
        for receipt in r['receipts']:
            doc = report_body(dart, receipt)
            if doc and extract(doc, kind, period_end=r['period_end'], receipt=receipt, subtype=subtype):
                reports.append({'kind': r['kind'], 'period_end': r['period_end'], 'receipt': receipt, 'doc': doc})
                break
    if not reports:
        return None, f'{kind}:no_report_body'
    res = regulatory_from_reports(reports, kind=kind, subtype=subtype)
    if not res:
        return None, f'{kind}:table_not_found'
    return res, f'{kind}:{len(res["series"])}_periods'


def notes_packet(dart: Dart, year: int, fs: str, fy_rows: list) -> tuple[dict | None, str]:
    """연구개발비·자산화, 주식보상, 재고평가손실, 충당부채 종류별 (dart_kfa/note_items.py)."""
    from dart_kfa.note_items import note_items  # noqa: E402
    from dart_kfa.segments import labels_from_zip  # noqa: E402
    from dart_kfa.xbrl_notes import instance_from_zip  # noqa: E402
    receipt = fy_rows[0].get('rcept_no') if fy_rows else None
    blob = dart.get_bytes('fnlttXbrl.xml', rcept_no=receipt, reprt_code=REPRT['FY']) if receipt else None
    if not blob:
        return None, 'no_xbrl'
    revenue = next((num(r.get('thstrm_amount')) for sj in ('IS', 'CIS') for r in fy_rows
                    if r.get('sj_div') == sj and r.get('account_id') == 'ifrs-full_Revenue'), None)
    res = note_items(instance_from_zip(blob), fs_div=fs, fiscal_year_end=f'{year}-12-31',
                     labels=labels_from_zip(blob), revenue=revenue)
    res['receipt'] = receipt
    found = [k for k in ('rd_expensed', 'rd_capitalised', 'sbc', 'inventory_writedown') if (res.get(k) or {}).get('value') is not None]
    if res.get('provisions'):
        found.append('provisions')
    return (res if found else None), ','.join(found) or 'none'


def segments_packet(dart: Dart, year: int, fs: str, fy_rows: list) -> tuple[dict | None, str]:
    """사업부문 / 제품 / 지역 breakdowns from the FY XBRL (dart_kfa/segments.py)."""
    from dart_kfa.segments import labels_from_zip, segment_breakdowns  # noqa: E402
    from dart_kfa.xbrl_notes import instance_from_zip  # noqa: E402
    receipt = fy_rows[0].get('rcept_no') if fy_rows else None
    blob = dart.get_bytes('fnlttXbrl.xml', rcept_no=receipt, reprt_code=REPRT['FY']) if receipt else None
    if not blob:
        return None, 'no_xbrl'
    face = next((num(r.get('thstrm_amount')) for sj in ('IS', 'CIS') for r in fy_rows
                 if r.get('sj_div') == sj and r.get('account_id') == 'ifrs-full_Revenue'), None)
    res = segment_breakdowns(instance_from_zip(blob), fs_div=fs, fiscal_year_end=f'{year}-12-31',
                             labels=labels_from_zip(blob), face_revenue=face)
    res['receipt'] = receipt
    kinds = ','.join(f"{b['kind']}{'' if b['reconciles'] else '?'}" for b in res['breakdowns']) or 'none'
    return (res if res['breakdowns'] else None), kinds


def financial_packet(dart: Dart, corp: str, year: int, company: dict, fy_rows: list) -> tuple[dict | None, str]:
    """업권 지표 (dart_kfa/financial_kpis.py): face-statement ratios + reported
    asset-quality / margin tables from the newest periodic report."""
    from dart_kfa.entity_policy import classify_entity  # noqa: E402
    from dart_kfa.financial_kpis import financial_kpis, reported_ratios  # noqa: E402
    from dart_kfa.regulatory_capital import regulatory_kind  # noqa: E402
    name = company.get('corp_name') or ''
    policy = classify_entity({'corp_code': corp, 'induty_code': company.get('induty_code'), 'corp_name': name})
    kind, _ = regulatory_kind(policy.get('entity_class'), name)
    if not kind:
        return None, 'not_regulated_financial'
    doc = receipt = period_end = None
    for r in periodic_reports(dart, corp, year)[:3]:
        body = report_body(dart, r['receipts'][0])
        if body and reported_ratios(body, kind):
            doc, receipt, period_end = body, r['receipts'][0], r['period_end']
            break
    res = financial_kpis(fy_rows, kind=kind, doc=doc, receipt=receipt, period_end=period_end)
    res['fiscal_year'] = year
    return res, f"{kind}:reported={','.join(sorted(res['reported'])) or 'none'}"


def backlog_packet(dart: Dart, corp: str, year: int, bases: dict) -> tuple[dict | None, str]:
    """수주잔고 from the newest periodic report that has a parseable table."""
    from dart_kfa.order_backlog import backlog_from_report  # noqa: E402
    last = 'no_periodic_report'
    for r in periodic_reports(dart, corp, year)[:3]:
        doc = report_body(dart, r['receipts'][0])
        if not doc:
            continue
        got = backlog_from_report(doc, receipt=r['receipts'][0], period_end=r['period_end'])
        last = f"{r['kind']}:{got['status']}"
        if got['status'] == 'no_section':
            return None, last
        if got['status'] == 'parsed':
            got['report'] = r['kind']
            ltm = bases.get('ltm') or {}
            fy = bases.get('fy') or {}
            rev = ltm.get('revenue') if ltm.get('revenue') else fy.get('revenue')
            if rev and rev > 0:
                got['backlog_to_revenue'] = got['backlog'] / rev
                got['revenue_basis'] = f"LTM ~{ltm['period_end']}" if ltm.get('revenue') else f"FY{year}"
            if got.get('new_orders') is not None and got.get('delivered'):
                got['book_to_bill'] = got['new_orders'] / got['delivered']
            return got, f"{r['kind']}:{r['period_end']}"
    return None, last


def investor_packet(dart: Dart, corp: str, year: int, fs: str, fy_rows: list, prior: list,
                    result: dict, bases: dict, xbrl_packs: list) -> tuple[dict | None, str]:
    """Growth / ROIC / Z / F-score, shareholder returns, CB dilution and the EV
    bridge (dart_kfa/investor_metrics.py) from data this run already fetched
    plus three structured endpoints and the latest periodic report body."""
    from dart_kfa.investor_metrics import dilution_from_report, investor_metrics, lease_from_instance  # noqa: E402
    from dart_kfa.xbrl_notes import instance_from_zip, parse_instance  # noqa: E402
    fy_reports = {year: fy_rows}
    for p in prior:
        fy_reports[int(p['fiscal_year_end'][:4])] = p['filings']['FY']['response']['list']
    financial = result.get('industry') == 'financial'
    alot = dart.get('alotMatter.json', corp_code=corp, bsns_year=str(year), reprt_code=REPRT['FY'])
    tess = dart.get('tesstkAcqsDspsSttus.json', corp_code=corp, bsns_year=str(year), reprt_code=REPRT['FY'])
    shares = dart.get('stockTotqySttus.json', corp_code=corp, bsns_year=str(year), reprt_code=REPRT['FY'])
    issued = next((num(r.get('istc_totqy')) for r in shares.get('list') or [] if _se(r) in COMMON_LABELS), None)
    # Outstanding convertibles: newest periodic report whose body has the section.
    # Q1/Q3 reports may omit the capital section; walk back to H1 / FY.
    dilution, dil_note = None, 'no_periodic_report'
    for r in periodic_reports(dart, corp, year):
        for receipt in r['receipts'][:2]:
            doc = report_body(dart, receipt)
            if not doc:
                continue
            got = dilution_from_report(doc, receipt=receipt, period_end=r['period_end'])
            dil_note = f"{r['kind']}:{r['period_end']}:{got['status']}"
            if got['status'] != 'undetermined':
                dilution = got
                break
        if dilution:
            break
    cards = result.get('cards') or {}
    nd = cards.get('net_debt') or {}
    ndr = cards.get('net_debt_reported') or {}
    lease_in = nd.get('value') is not None or any(str(i.get('input', '')).startswith('lease_') for i in ndr.get('inputs') or [])
    xbrl_lease = xbrl_lease_basis = None
    if not lease_in and fy_rows:
        blob = dart.get_bytes('fnlttXbrl.xml', rcept_no=fy_rows[0].get('rcept_no'), reprt_code=REPRT['FY'])
        if blob:
            try:
                ctx, facts = parse_instance(instance_from_zip(blob))
                xbrl_lease, xbrl_lease_basis = lease_from_instance(ctx, facts, fs_div=fs, instant=f'{year}-12-31')
            except Exception as exc:  # noqa: BLE001 -- the bridge then shows the lease as unknown
                print(f'  xbrl lease {corp}: {type(exc).__name__}: {exc}', file=sys.stderr)
    fyb = bases.get('fy') or {}
    overrides = {}
    for pack in xbrl_packs:
        for row in (pack or {}).get('rows') or []:
            if row['key'] in ('receivables',) and row.get('period_start') is None:
                overrides.setdefault(int(row['period_end'][:4]), {})['receivables'] = row['amount'] * row.get('scale', 1)
            # D&A from the notes where the cash-flow statement is summarised
            # (고려아연, 삼성전자): feeds the mining kit's D&A ratios.
            if row['key'] in ('PPE_DEPRECIATION', 'INTANGIBLE_AMORTIZATION') and row.get('period_start'):
                y = overrides.setdefault(int(row['period_end'][:4]), {})
                y['cf_dep_amort_total'] = y.get('cf_dep_amort_total', 0) + row['amount'] * row.get('scale', 1)
    out = investor_metrics(
        fy_reports, fiscal_year=year, financial=financial,
        dividends_rows=alot.get('list') if alot.get('status') == '000' else None,
        treasury_rows=tess.get('list') if tess.get('status') == '000' else None,
        dilution=dilution, issued_common=issued, lease_in_net_debt=lease_in, xbrl_lease=xbrl_lease,
        xbrl_lease_basis=xbrl_lease_basis, ebitda=fyb.get('ebitda'), ebitda_card=fyb.get('ebitda_card'),
        balance_overrides=overrides, kit=result.get('industry'))
    out['inputs'] = {'fy_reports': sorted(fy_reports), 'dividends': alot.get('status'), 'treasury': tess.get('status'),
                     'dilution': dil_note, 'issued_common_source': 'stockTotqySttus FY istc_totqy' if issued else None}
    return out, f"years={out['years'][0] if out['years'] else '-'}..{year} dilution={dil_note}"


ISSUER_KITS = ENGINE / 'config' / 'kfa_issuer_kits.json'
TRADING_NAME = re.compile(r'인터내셔널|상사|코퍼레이션')


def issuer_kit(corp: str, company: dict) -> str | None:
    """Kit the KSIC code cannot tell: a 종합상사 is filed as 상품 중개업 (G461,
    the platform kit) or 종합 도매업. Reviewed overrides first, then the
    name rule. None leaves the engine's KSIC routing alone."""
    if ISSUER_KITS.exists():
        kit = (json.loads(ISSUER_KITS.read_text()).get('overrides') or {}).get(corp)
        if kit:
            return kit
    code = str(company.get('induty_code') or '')
    if code.startswith(('461', '467', '468')) and TRADING_NAME.search(company.get('corp_name') or ''):
        return 'trading_house'
    return None


def build_one(dart: Dart, corp: str, stock: str | None, today: dt.date) -> dict:
    company = dart.get('company.json', corp_code=corp)
    if company.get('status') != '000':
        raise RuntimeError(f'company.json {company.get("status")}')
    year, fs = pick_basis(dart, corp, today)
    filings = {b: report(dart, corp, year, b, fs) for b in ('FY', 'Q1', 'H1', 'Q3')}
    prior = []
    for y in (year - 1, year - 2):
        r = report(dart, corp, y, 'FY', fs)
        if r['response']['status'] == '000':
            prior.append({'fiscal_year_end': f'{y}-12-31', 'filings': {'FY': r}})
    fund, fund_note = funding_packet(dart, corp, year, filings['FY']['response']['list'], fs)
    payload = {
        'entity_id': corp, 'fiscal_year_end': f'{year}-12-31', 'fs_div': fs, 'currency': 'KRW',
        'corp': {'induty_code': company.get('induty_code'), 'corp_name': company.get('corp_name'),
                 'corp_cls': company.get('corp_cls'), 'stock_code': (company.get('stock_code') or '').strip() or None},
        'filings': filings, 'prior_reports': prior,
    }
    kit = issuer_kit(corp, company)
    if kit:
        payload['industry'] = kit
    if fund:
        payload['funding'] = fund
    fy_rows = filings['FY']['response']['list']
    if any(str(r.get('account_id', '')).startswith('ifrs-full_') for r in fy_rows):
        payload['corp']['accounting_basis'] = 'K-IFRS'   # statements tagged in the IFRS taxonomy
    stock = stock or payload['corp']['stock_code']
    market_note = 'unlisted'
    if stock:
        market, market_note = market_packet(dart, corp, stock, fy_rows[0].get('rcept_no') or '', today)
        if market:
            payload['market'] = market
    # Reviewed note bundles (D&A, P&L interest, ...) are the engine's only
    # source for strict EBITDA -- it deliberately does not lift D&A from the
    # cash-flow add-backs on its own. Pass every bundle that matches this
    # company, year and basis exactly.
    reviewed = [b for b in (json.loads(f.read_text()) for f in sorted((ENGINE / 'config' / 'pe_cr_reviewed').glob('*.json')))
                if b.get('source') == 'DART' and b.get('entity_id') == corp and b.get('fs_div') == fs
                and b.get('fiscal_year_end') == f'{year}-12-31']
    sys.path.insert(0, str(ENGINE))
    from build_pe_cr import build  # noqa: E402  (engine lives outside this package)
    from dart_kfa.xbrl_notes import instance_from_zip, merge_packs, note_bundle  # noqa: E402

    # Note facts (D&A, P&L interest, interest income) from each FY's original
    # XBRL. The current year's pack feeds strict EBITDA / ICR / EBIT; prior
    # years' packs feed the 3-year 이자보상배율 test in the CR screen.
    def xbrl_pack(fy: int, rows: list) -> dict | None:
        receipt = rows[0].get('rcept_no') if rows else None
        if not receipt:
            return None
        blob = dart.get_bytes('fnlttXbrl.xml', rcept_no=receipt, reprt_code=REPRT['FY'])
        if not blob:
            return None
        try:
            return note_bundle(instance_from_zip(blob), entity_id=corp, fs_div=fs,
                               fiscal_year_end=f'{fy}-12-31', receipt=receipt)
        except Exception as exc:
            print(f'  xbrl {corp} FY{fy}: {type(exc).__name__}: {exc}', file=sys.stderr)
            return None

    current_xbrl = xbrl_pack(year, filings['FY']['response']['list'])
    pack = merge_packs(reviewed[0] if reviewed else None, current_xbrl)
    if pack:
        payload['reviewed_disclosures'] = pack
    prior_packs = {}
    for p in prior:
        fy = int(p['fiscal_year_end'][:4])
        pp = xbrl_pack(fy, p['filings']['FY']['response']['list'])
        if pp:
            prior_packs[p['fiscal_year_end']] = pp
    if prior_packs:
        payload['screen_inputs'] = {'annual_reviewed_disclosures': prior_packs}
    result = build(payload, 'annual')
    regulatory, regulatory_note = regulatory_series(dart, corp, year, company, fs)
    bases = valuation_bases(dart, corp, year, fs, fy_rows, result.get('cards') or {})
    try:
        quarterly, quarterly_note = quarterly_packet(dart, corp, year, fs, filings, stock, today)
    except Exception as exc:  # noqa: BLE001
        quarterly, quarterly_note = None, f'error:{type(exc).__name__}: {exc}'[:200]
    try:
        notes, notes_note = notes_packet(dart, year, fs, fy_rows)
    except Exception as exc:  # noqa: BLE001
        notes, notes_note = None, f'error:{type(exc).__name__}: {exc}'[:200]
    try:
        segments, segments_note = segments_packet(dart, year, fs, fy_rows)
    except Exception as exc:  # noqa: BLE001
        segments, segments_note = None, f'error:{type(exc).__name__}: {exc}'[:200]
    try:
        fin_kpis, fin_note = financial_packet(dart, corp, year, company, fy_rows)
    except Exception as exc:  # noqa: BLE001
        fin_kpis, fin_note = None, f'error:{type(exc).__name__}: {exc}'[:200]
    try:
        backlog, backlog_note = backlog_packet(dart, corp, year, bases)
    except Exception as exc:  # noqa: BLE001
        backlog, backlog_note = None, f'error:{type(exc).__name__}: {exc}'[:200]
    try:
        investor, investor_note = investor_packet(dart, corp, year, fs, fy_rows, prior, result, bases,
                                                   [current_xbrl, *prior_packs.values()])
    except Exception as exc:  # noqa: BLE001 -- the PE/CR snapshot still publishes
        investor, investor_note = None, f'error:{type(exc).__name__}: {exc}'[:200]
    receipts = {b: (r['response']['list'][0].get('rcept_no') if r['response']['list'] else None) for b, r in filings.items()}
    return {
        'schema': 'kfa_pecr_snapshot/1',
        'generated_at': today.isoformat(),
        'engine': 'New for anti/scripts/dart/build_pe_cr.py',
        'engine_commit': subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'],
                                        capture_output=True, text=True).stdout.strip() or None,
        'corp_code': corp, 'stock_code': stock, 'entity': company.get('corp_name'),
        'induty_code': company.get('induty_code'), 'fiscal_year': year, 'fs_div': fs,
        'receipts': receipts, 'prior_years': [p['fiscal_year_end'][:4] for p in prior],
        'funding_input': fund_note,
        'market_input': market_note,
        'reviewed_disclosures': {'hand_reviewed': len(reviewed),
                                 'xbrl_note_keys': sorted(r['key'] for r in (current_xbrl or {}).get('rows', [])),
                                 'prior_years_with_xbrl_notes': sorted(prior_packs)},
        'pe_cr': result,
        'regulatory': regulatory,
        'valuation_bases': bases,
        'investor_metrics': investor,
        'segments': segments,
        'note_items': notes,
        'quarterly': quarterly,
        'quarterly_input': quarterly_note,
        'note_items_input': notes_note,
        'segments_input': segments_note,
        'order_backlog': backlog,
        'order_backlog_input': backlog_note,
        'financial_kpis': fin_kpis,
        'financial_kpis_input': fin_note,
        'investor_input': investor_note,
        'regulatory_input': regulatory_note,
    }


# Bump when the snapshot's content changes, so every company is rebuilt once.
BUILDER_VERSION = '2026-11-26.1'
NAVER_RANK = 'https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100'
EXTRA_TARGETS = ROOT / 'New for anti' / 'scripts' / 'dart' / 'config' / 'kfa_pecr_extra_targets.json'


def universe(spec: str) -> list[str]:
    """'KOSPI:200,KOSDAQ:150' -> the largest common stocks by 시가총액 (Naver ranking, no key)."""
    codes = []
    for part in filter(None, spec.split(',')):
        market, _, n = part.partition(':')
        want, page = int(n or 100), 1
        got = []
        while len(got) < want and page <= 40:
            req = urllib.request.Request(NAVER_RANK.format(market=market.upper(), page=page),
                                         headers={'User-Agent': 'Mozilla/5.0 (compatible; global-trade-dashboard/1.0)'})
            with urllib.request.urlopen(req, timeout=30) as res:
                rows = json.loads(res.read()).get('stocks') or []
            if not rows:
                break
            got += [r['itemCode'] for r in rows if r.get('stockEndType') == 'stock' and re.fullmatch(r'\d{5}0', r.get('itemCode') or '')]
            page += 1
            time.sleep(0.2)
        codes += got[:want]
    return codes


def corp_codes_by_stock(dart: Dart) -> dict:
    """KRX code -> DART corp_code from OpenDART corpCode.xml (one zip)."""
    import io
    import xml.etree.ElementTree as ET
    import zipfile
    blob = dart.get_bytes('corpCode.xml')
    if not blob:
        raise RuntimeError('corpCode.xml unavailable')
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        root = ET.fromstring(z.read(z.namelist()[0]))
    return {(e.findtext('stock_code') or '').strip(): e.findtext('corp_code')
            for e in root.iter('list') if (e.findtext('stock_code') or '').strip()}


def latest_periodic_receipt(dart: Dart, corp: str, today: dt.date) -> str | None:
    lst = dart.get('list.json', corp_code=corp, bgn_de=(today - dt.timedelta(days=430)).strftime('%Y%m%d'),
                   pblntf_ty='A', page_count=20)
    rows = [r for r in lst.get('list') or [] if REPORT_NAME.search(r.get('report_nm') or '')]
    return max((r['rcept_no'] for r in rows), default=None)


def compact_parts(inputs: list) -> list:
    """The card's inputs as the detail box shows them: what, how much, from which
    account / report / date. The full canonical provenance (~75 % of the file)
    is dropped; the receipts kept make the run reproducible."""
    parts = []
    for i in inputs or []:
        if not isinstance(i, dict):
            continue
        if i.get('input') == 'market_observation':
            parts.append({'input': 'market', 'market_cap': i.get('market_cap'),
                          'preferred_equity': i.get('preferred_equity'), 'as_of': i.get('as_of')})
            continue
        pv = i.get('provenance') or {}
        parts.append({k: v for k, v in {
            'input': i.get('input'), 'label': pv.get('source_account_name') or i.get('input'),
            'value': i.get('value'), 'period_end': i.get('period_end'), 'opening': i.get('opening') or None,
            'filing': pv.get('filing_id'), 'report': i.get('report_code'),
        }.items() if v is not None})
    return parts


def slim(snap: dict) -> dict:
    for card in ((snap.get('pe_cr') or {}).get('cards') or {}).values():
        if isinstance(card, dict) and isinstance(card.get('inputs'), list):
            card['parts'] = compact_parts(card.pop('inputs'))
    return snap


def naver_monthly(code: str) -> dict:
    """{'YYYYMM': close} for ~4 years from Naver's chart feed (no key)."""
    from dart_kfa.quarterly import parse_fchart
    url = f'https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=month&count=48&requestType=0'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; global-trade-dashboard/1.0)'})
    with urllib.request.urlopen(req, timeout=30) as res:
        return parse_fchart(res.read().decode('euc-kr', 'ignore'))


def quarterly_packet(dart: Dart, corp: str, year: int, fs: str, filings: dict, stock: str | None,
                     today: dt.date) -> tuple[dict | None, str]:
    """Quarter-end EV and its parts (dart_kfa/quarterly.py) from the reports this
    run already fetched, plus monthly closes for the market cap."""
    from dart_kfa.quarterly import dart_points, series  # noqa: E402
    rows = lambda r: r['response']['list'] if r['response']['status'] == '000' else []  # noqa: E731
    quarters = {b: rows(filings[b]) for b in ('Q1', 'H1', 'Q3')}
    nxt = {b: rows(report(dart, corp, year + 1, b, fs)) for b in ('Q1', 'H1', 'Q3')}
    points = dart_points(year, rows(filings['FY']), None, quarters, nxt)
    closes = pref_closes = shares = pref_shares = None
    if stock:
        srows, _ = share_rows(dart, corp, today)
        for r in srows:
            se = _se(r)
            if se in COMMON_LABELS:
                shares = num(r.get('istc_totqy'))
            elif se in ('우선주', '우선주식'):
                pref_shares = num(r.get('istc_totqy'))
        try:
            closes = naver_monthly(stock)
            if pref_shares:
                pref_closes = naver_monthly(stock[:-1] + '5')
        except Exception as exc:  # noqa: BLE001 -- the balances still publish
            print(f'  monthly prices {stock}: {exc}', file=sys.stderr)
    res = series(points, closes=closes, shares=shares, pref_closes=pref_closes, pref_shares=pref_shares)
    res['shares'] = {'common': shares, 'preferred': pref_shares}
    return (res if res['points'] else None), f"{len(res['points'])}_quarters"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('corp_codes', nargs='*', help='default: the validation set in DEFAULT_TARGETS')
    ap.add_argument('--cache', type=Path, default=Path(os.environ.get('TMPDIR', '/tmp')) / 'kfa_pecr_cache')
    ap.add_argument('--universe', default='', help="add the largest listed companies, e.g. 'KOSPI:200,KOSDAQ:150'")
    ap.add_argument('--max-calls', type=int, default=None, help='stop cleanly after this many OpenDART requests')
    ap.add_argument('--skip-fresh', action='store_true',
                    help='skip a company whose snapshot already has its newest periodic report and this builder version')
    ap.add_argument('--workers', type=int, default=1, help='companies built in parallel (OpenDART latency bound)')
    ap.add_argument('--max-minutes', type=float, default=None,
                    help='start no new company after this many minutes, so a CI job always reaches its commit step')
    args = ap.parse_args()
    key = os.environ.get('DART_API_KEY', '').strip()
    if not key:
        print('DART_API_KEY is not set', file=sys.stderr)
        return 2
    dart, today = Dart(key, args.cache, args.max_calls), dt.date.today()
    targets = list(DEFAULT_TARGETS) if not args.corp_codes else [(c, None, c) for c in args.corp_codes]
    if not args.corp_codes and EXTRA_TARGETS.exists():
        targets += [(c, None, c) for c in json.loads(EXTRA_TARGETS.read_text()).get('corp_codes', [])]
    if args.universe:
        by_stock = corp_codes_by_stock(dart)
        for code in universe(args.universe):
            if by_stock.get(code):
                targets.append((by_stock[code], code, code))
    seen, ordered = set(), []
    for t in targets:
        if t[0] not in seen:
            seen.add(t[0])
            ordered.append(t)
    # Companies with no snapshot first, so a short budget widens coverage.
    ordered.sort(key=lambda t: (OUT_DIR / f'{t[0]}_v1.json').exists())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index, failed = {}, {}
    state = {'skipped': 0, 'stop': None}
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock()

    def work(target):
        corp, stock, label = target
        if state['stop'] or (deadline and time.monotonic() > deadline):
            state['stop'] = state['stop'] or f'--max-minutes {args.max_minutes} reached'
            return
        path = OUT_DIR / f'{corp}_v1.json'
        try:
            if args.skip_fresh and path.exists():
                old = json.loads(path.read_text())
                newest = latest_periodic_receipt(dart, corp, today)
                if old.get('builder_version') == BUILDER_VERSION and newest and newest == old.get('latest_periodic_receipt'):
                    with lock:
                        state['skipped'] += 1
                    return
            snap = build_one(dart, corp, stock, today)
            snap['builder_version'] = BUILDER_VERSION
            snap['latest_periodic_receipt'] = latest_periodic_receipt(dart, corp, today)
            slim(snap)
        except BudgetExhausted as exc:
            state['stop'] = f'budget: {exc}'
            return
        except Exception as exc:  # one company must not stop the batch
            with lock:
                failed[corp] = f'{type(exc).__name__}: {str(exc).replace(key, "<key>")}'[:300]
            print(f'FAIL {label} {corp}: {failed[corp]}', file=sys.stderr, flush=True)
            return
        path.write_text(json.dumps(snap, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n')
        with lock:
            index[corp] = {'entity': snap['entity'], 'stock_code': stock or (snap.get('stock_code')), 'fiscal_year': snap['fiscal_year'],
                           'fs_div': snap['fs_div'], 'industry': snap['pe_cr'].get('industry'),
                           'financial': snap['pe_cr'].get('industry') == 'financial'}
        print(f'ok   {label} {corp} FY{snap["fiscal_year"]} {snap["fs_div"]} {snap["pe_cr"].get("industry")} '
              f'investor={snap["investor_input"]} segments={snap["segments_input"]} backlog={snap["order_backlog_input"]} '
              f'fin={snap["financial_kpis_input"]}', file=sys.stderr, flush=True)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        list(pool.map(work, ordered))
    if state['stop']:
        print(f'STOP {state["stop"]} after {dart.calls} calls', file=sys.stderr)
    skipped = state['skipped']
    idx_path = OUT_DIR / 'index_v1.json'
    prev = json.loads(idx_path.read_text())['index'] if idx_path.exists() else {}
    prev.update(index)
    idx_path.write_text(json.dumps({'schema': 'kfa_pecr_index/1', 'generated_at': today.isoformat(),
                                    'count': len(prev), 'index': dict(sorted(prev.items()))},
                                   ensure_ascii=False, indent=1) + '\n')
    print(f'{len(index)} written, {skipped} fresh, {len(failed)} failed, {dart.calls} OpenDART calls', file=sys.stderr)
    # A batch over hundreds of filers always has a few odd ones; fail the run only
    # when nothing could be built.
    return 0 if index or skipped or not failed else 1


if __name__ == '__main__':
    sys.exit(main())
