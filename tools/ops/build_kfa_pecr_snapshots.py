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
    ('00688996', '105560', 'KB금융'),          # 금융: 은행지주
]

FUNDING_ENDPOINTS = {
    'corporate_bond': 'cprndNrdmpBlce',
    'commercial_paper': 'entrprsBilScritsNrdmpBlce',
    'short_term_bond': 'srtpdPsndbtNrdmpBlce',
}
FUNDING_LABEL = {'corporate_bond': '회사채', 'commercial_paper': '기업어음(CP)', 'short_term_bond': '단기사채'}
REPRT = {'FY': '11011', 'Q1': '11013', 'H1': '11012', 'Q3': '11014'}


class Dart:
    def __init__(self, key: str, cache: Path):
        self.key, self.cache = key, cache
        cache.mkdir(parents=True, exist_ok=True)

    def get_bytes(self, path: str, **params) -> bytes | None:
        """Binary endpoint (fnlttXbrl.xml zip), cached; None on an API error body."""
        name = path.replace('.xml', '') + '_' + '_'.join(f'{k}={v}' for k, v in sorted(params.items())) + '.bin'
        hit = self.cache / name
        if hit.exists():
            data = hit.read_bytes()
            return data or None
        q = urllib.parse.urlencode({'crtfc_key': self.key, **params})
        for attempt in range(3):
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
            try:
                req = urllib.request.Request(f'{API}/{path}?{q}', headers={'User-Agent': 'global-trade-dashboard/1.0'})
                with urllib.request.urlopen(req, timeout=40) as res:
                    data = json.loads(res.read())
            except Exception as exc:
                print(f'  retry {path}: {str(exc).replace(self.key, "<key>")}', file=sys.stderr)
                time.sleep(2 * (attempt + 1))
                continue
            if data.get('status') == '020':
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
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('corp_codes', nargs='*', help='default: the validation set in DEFAULT_TARGETS')
    ap.add_argument('--cache', type=Path, default=Path(os.environ.get('TMPDIR', '/tmp')) / 'kfa_pecr_cache')
    args = ap.parse_args()
    key = os.environ.get('DART_API_KEY', '').strip()
    if not key:
        print('DART_API_KEY is not set', file=sys.stderr)
        return 2
    targets = DEFAULT_TARGETS if not args.corp_codes else [(c, None, c) for c in args.corp_codes]
    dart, today = Dart(key, args.cache), dt.date.today()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index, failed = {}, {}
    for corp, stock, label in targets:
        try:
            snap = build_one(dart, corp, stock, today)
        except Exception as exc:  # one company must not stop the batch
            failed[corp] = f'{type(exc).__name__}: {str(exc).replace(key, "<key>")}'[:300]
            print(f'FAIL {label} {corp}: {failed[corp]}', file=sys.stderr)
            continue
        (OUT_DIR / f'{corp}_v1.json').write_text(json.dumps(snap, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n')
        index[corp] = {'entity': snap['entity'], 'stock_code': stock or (snap.get('stock_code')), 'fiscal_year': snap['fiscal_year'],
                       'fs_div': snap['fs_div'], 'industry': snap['pe_cr'].get('industry'),
                       'financial': snap['pe_cr'].get('industry') == 'financial'}
        print(f'ok   {label} {corp} FY{snap["fiscal_year"]} {snap["fs_div"]} funding={snap["funding_input"]} market={snap["market_input"]}', file=sys.stderr)
    idx_path = OUT_DIR / 'index_v1.json'
    prev = json.loads(idx_path.read_text())['index'] if idx_path.exists() else {}
    prev.update(index)
    idx_path.write_text(json.dumps({'schema': 'kfa_pecr_index/1', 'generated_at': today.isoformat(),
                                    'count': len(prev), 'index': dict(sorted(prev.items()))},
                                   ensure_ascii=False, indent=1) + '\n')
    print(f'{len(index)} written, {len(failed)} failed', file=sys.stderr)
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
