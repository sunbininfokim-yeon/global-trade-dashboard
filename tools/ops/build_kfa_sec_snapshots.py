#!/usr/bin/env python3
"""US counterpart of build_kfa_pecr_snapshots.py: engine snapshots from SEC.

For each US filer it fetches SEC companyfacts (one file, no key) and the
submissions record (SIC code, fiscal-year end), then:

  * runs the PE/CR engine's own SEC path (build_pe_cr.build, source=SEC) with
    the filer's real fiscal-period layout (52/53-week years included);
  * converts the 10-K facts to the row shape of the investor / financial
    modules (dart_kfa/sec_rows.py) and runs investor_metrics (growth, ROIC,
    DuPont, accruals, Altman, Piotroski, dividends + buy-backs, EV bridge),
    financial_kpis for banks / insurers / brokers / card lenders;
  * adds the US-only items: RPO backlog, diluted-vs-basic share gap, SBC, R&D;
  * stores the FY / LTM denominators for the browser's market multiples.

Output: New for anti/public/data/kfa_pecr/us_<TICKER>_v1.json and index entries
keyed us_<TICKER> (industry kit from the SIC code). Segment breakdowns are not
available: companyfacts carries no dimensional facts.

Universe: Naver's NASDAQ / NYSE 시가총액 ranking (no key), mapped to CIKs with
SEC's company_tickers.json. Filers without US-GAAP 10-K facts (20-F foreign
issuers such as TSMC) are skipped.

SEC asks automated clients to identify themselves; the User-Agent comes from
$SEC_USER_AGENT, with a generic default.

Usage:
    python3 tools/ops/build_kfa_sec_snapshots.py [TICKER ...] [--universe NASDAQ:100,NYSE:100]
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
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'New for anti' / 'scripts' / 'dart'
OUT_DIR = ROOT / 'New for anti' / 'public' / 'data' / 'kfa_pecr'
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

BUILDER_VERSION = '2026-11-24.us1'
UA = os.environ.get('SEC_USER_AGENT') or 'global-trade-dashboard research client'
NAVER_US = 'https://api.stock.naver.com/stock/exchange/{market}/marketValue?page={page}&pageSize=100'
DEFAULT = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'JPM', 'BAC', 'WMT', 'COST', 'LLY', 'JNJ',
           'XOM', 'BA', 'CAT', 'KO', 'NFLX', 'INTC', 'AMD']


def fetch(url: str, cache: Path | None = None, ua: str = UA) -> bytes:
    if cache and cache.exists() and cache.stat().st_size:
        return cache.read_bytes()
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as res:
                data = res.read()
            time.sleep(0.15)          # SEC fair-access: well under 10 requests/second
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
            return data
        except Exception as exc:      # noqa: BLE001 -- retried, then raised
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'{url}: {last}')


def universe(spec: str) -> list[tuple[str, str]]:
    """'NASDAQ:100,NYSE:100' -> [(ticker, reuters code)] by 시가총액."""
    out = []
    for part in filter(None, spec.split(',')):
        market, _, n = part.partition(':')
        want, page, got = int(n or 100), 1, []
        while len(got) < want and page <= 40:
            rows = json.loads(fetch(NAVER_US.format(market=market.upper(), page=page),
                                    ua='Mozilla/5.0 (compatible; global-trade-dashboard/1.0)')).get('stocks') or []
            if not rows:
                break
            got += [((r.get('symbolCode') or '').replace(' ', '-').replace('.', '-'), r.get('reutersCode'))
                    for r in rows if r.get('stockEndType') == 'stock' and r.get('symbolCode')]
            page += 1
        out += got[:want]
    return out


def reuters_for(ticker: str, exchange: str | None) -> str:
    return f'{ticker}.O' if (exchange or '').upper().startswith('NASDAQ') else ticker.replace('-', '')


def merge_predecessor(facts: dict, cik10: str, cache: Path) -> tuple[dict, list[str]]:
    """A holding-company reorganisation (ExxonMobil, 2026) moves the ticker to a
    new registrant whose companyfacts carry only the filings since; the 10-K
    history stays under the old CIK. The new filer's facts cite those earlier
    filings by accession number (0000034088-26-...), so the predecessor is
    found from the accession prefixes and its facts are merged in, newest
    filing winning on duplicates."""
    gaap = (facts.get('facts') or {}).get('us-gaap') or {}
    prefixes = {str(p.get('accn') or '')[:10] for c in gaap.values() for pts in (c.get('units') or {}).values() for p in pts}
    prefixes = sorted(x for x in prefixes if x.isdigit() and x != cik10)
    merged_from = []
    for old in prefixes[:2]:
        try:
            prior = json.loads(fetch(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{old}.json', cache / f'facts_{old}.json'))
        except Exception:      # noqa: BLE001 -- an accession prefix can be a filing agent, not a filer
            continue
        pg = (prior.get('facts') or {}).get('us-gaap') or {}
        if not pg:
            continue
        for concept, body in pg.items():
            dest = gaap.setdefault(concept, {'units': {}})
            for unit, pts in (body.get('units') or {}).items():
                have = {(q.get('accn'), q.get('start'), q.get('end'), q.get('val')) for q in dest['units'].get(unit, [])}
                dest['units'].setdefault(unit, []).extend(
                    q for q in pts if (q.get('accn'), q.get('start'), q.get('end'), q.get('val')) not in have)
        merged_from.append(old)
    return facts, merged_from


def build_one(ticker: str, cik: str, reuters: str | None, cache: Path, today: dt.date) -> dict:
    from build_pe_cr import build  # noqa: E402
    from dart_kfa.financial_kpis import financial_kpis  # noqa: E402
    from dart_kfa.investor_metrics import investor_metrics  # noqa: E402
    from dart_kfa import sec_rows  # noqa: E402

    cik10 = cik.zfill(10)
    facts = json.loads(fetch(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json', cache / f'facts_{cik10}.json'))
    subm = json.loads(fetch(f'https://data.sec.gov/submissions/CIK{cik10}.json', cache / f'subm_{cik10}.json'))
    if not ((facts.get('facts') or {}).get('us-gaap')):
        raise RuntimeError('no us-gaap facts (foreign private issuer?)')
    ends = sec_rows.fiscal_year_ends(facts)
    predecessors = []
    if not ends or ends[-1] < (today - dt.timedelta(days=550)).isoformat():
        facts, predecessors = merge_predecessor(facts, cik10, cache)
        ends = sec_rows.fiscal_year_ends(facts)
    if not ends or ends[-1] < (today - dt.timedelta(days=550)).isoformat():
        raise RuntimeError('no recent 10-K')
    fye = ends[-1]
    fy = int(fye[:4])
    sic = subm.get('sic')
    kit = sec_rows.kit_for_sic(sic)
    fin_kind = sec_rows.financial_kind_for_sic(sic)
    financial = kit == 'financial'
    name = subm.get('name') or facts.get('entityName')
    exchange = (subm.get('exchanges') or [None])[0]
    reuters = reuters or reuters_for(ticker, exchange)

    payload = {'source': 'SEC', 'entity_id': cik10, 'companyfacts': facts, 'fiscal_year_end': fye,
               'report_periods': sec_rows.report_periods(facts, fye), 'fs_div': 'CFS', 'currency': 'USD',
               'corp': {'corp_name': name, 'industry_kit': kit, 'sic': sic}}
    if financial:
        payload['entity_policy'] = {'is_financial_entity': True}
    result = build(payload, 'annual')

    fy_reports = sec_rows.annual_rows(facts, ends)
    rows = fy_reports.get(fy) or []
    def row(aid):
        r = next((x for x in rows if x['account_id'] == aid), None)
        return float(r['thstrm_amount']) if r and r.get('thstrm_amount') not in (None, '') else None
    revenue = row('ifrs-full_Revenue')
    extras = sec_rows.us_extras(facts, fye, revenue)
    debt = sum(v for v in (row('ifrs-full_ShorttermBorrowings'), row('ifrs-full_CurrentPortionOfLongtermBorrowings'),
                           row('ifrs-full_LongtermBorrowings')) if v is not None)
    leases = sum(v for v in (row('ifrs-full_CurrentLeaseLiabilities'), row('ifrs-full_NoncurrentLeaseLiabilities')) if v is not None)
    cash = row('ifrs-full_CashAndCashEquivalents')
    op = row('dart_OperatingIncomeLoss')
    da = row('ifrs-full_AdjustmentsForDepreciationAndAmortisationExpense')
    if da is None:   # Microsoft tags depreciation and intangible amortization separately
        parts = [sec_rows._value(facts, [c], fye, True)[0] for c in ('Depreciation', 'AmortizationOfIntangibleAssets')]
        da = sum(p for p in parts if p is not None) if parts[0] is not None else None
    cfo = row('ifrs-full_CashFlowsFromUsedInOperatingActivities')
    capex = sum(v for v in (row('ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities'),
                            row('ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities')) if v is not None)
    ebitda = op + da if op is not None and da is not None and not financial else None
    net_debt = debt + leases - cash if cash is not None and not financial else None
    bases = {'fy': {'period_end': fye, 'receipt': f'SEC-10K-{fye}', 'revenue': revenue, 'operating_income': op,
                    'net_income_parent': row('ifrs-full_ProfitLossAttributableToOwnersOfParent'),
                    'net_income': row('ifrs-full_ProfitLoss'),
                    'parent_equity': row('ifrs-full_EquityAttributableToOwnersOfParent'), 'equity': row('ifrs-full_Equity'),
                    'ebitda': ebitda, 'ebitda_card': 'sec_op_plus_da' if ebitda is not None else None,
                    'net_debt': net_debt, 'net_debt_card': 'sec_debt_plus_operating_leases_minus_cash' if net_debt is not None else None,
                    'fcf': cfo - capex if cfo is not None else None, 'fcf_card': 'sec_cfo_minus_capex', 'cfo': cfo, 'cfo_card': 'sec'}}
    l = sec_rows.ltm(facts, fye)
    if l:
        bases['ltm'] = l
    investor = investor_metrics(fy_reports, fiscal_year=fy, financial=financial, dilution=extras.get('dilution'),
                                issued_common=(extras.get('dilution') or {}).get('issued_common'),
                                lease_in_net_debt=True, ebitda=ebitda, ebitda_card='sec_op_plus_da',
                                kit=result.get('industry'))
    fin = None
    if fin_kind:
        fin = financial_kpis(rows, kind=fin_kind)
        if fin:
            fin['fiscal_year'] = fy
    return {
        'schema': 'kfa_pecr_snapshot/1', 'source': 'SEC', 'currency': 'USD', 'market': 'US',
        'generated_at': today.isoformat(), 'builder_version': BUILDER_VERSION,
        'engine': 'New for anti/scripts/dart/build_pe_cr.py (source=SEC)',
        'engine_commit': subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'],
                                        capture_output=True, text=True).stdout.strip() or None,
        'corp_code': f'us_{ticker}', 'cik': cik10, 'ticker': ticker, 'stock_code': reuters, 'entity': name,
        'sic': sic, 'sic_description': subm.get('sicDescription'), 'exchange': exchange,
        'predecessor_ciks': predecessors or None,
        'fiscal_year': fy, 'fiscal_year_end': fye, 'fs_div': 'CFS',
        'receipts': {'FY': f'SEC-10K-{fye}'}, 'latest_filing': (subm.get('filings', {}).get('recent', {}).get('accessionNumber') or [None])[0],
        'market_input': 'naver_us_daily', 'pe_cr': result, 'valuation_bases': bases, 'investor_metrics': investor,
        'order_backlog': extras.get('backlog'), 'note_items': extras.get('note_items'), 'financial_kpis': fin,
        'segments': None, 'segments_input': 'not_in_sec_companyfacts',
    }


def main() -> int:
    from build_kfa_pecr_snapshots import slim  # noqa: E402
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tickers', nargs='*')
    ap.add_argument('--universe', default='', help="e.g. 'NASDAQ:150,NYSE:150'")
    ap.add_argument('--cache', type=Path, default=Path(os.environ.get('TMPDIR', '/tmp')) / 'kfa_sec_cache')
    ap.add_argument('--skip-fresh', action='store_true', help='skip when the newest SEC filing is unchanged')
    args = ap.parse_args()
    today = dt.date.today()
    tickers = json.loads(fetch('https://www.sec.gov/files/company_tickers.json', args.cache / 'company_tickers.json'))
    cik_by = {v['ticker'].upper(): str(v['cik_str']) for v in tickers.values()}
    targets = [(t.upper(), None) for t in (args.tickers or ([] if args.universe else DEFAULT))]
    if args.universe:
        targets += universe(args.universe)
    seen, built, failed, skipped = set(), {}, {}, 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ticker, reuters in targets:
        t = ticker.upper()
        if t in seen:
            continue
        seen.add(t)
        cik = cik_by.get(t) or cik_by.get(t.replace('-', '.'))
        if not cik:
            failed[t] = 'no CIK'
            continue
        path = OUT_DIR / f'us_{t}_v1.json'
        try:
            if args.skip_fresh and path.exists():
                old = json.loads(path.read_text())
                subm = json.loads(fetch(f'https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json'))
                newest = (subm.get('filings', {}).get('recent', {}).get('accessionNumber') or [None])[0]
                if old.get('builder_version') == BUILDER_VERSION and newest == old.get('latest_filing'):
                    skipped += 1
                    continue
            snap = slim(build_one(t, cik, reuters, args.cache, today))
        except Exception as exc:  # noqa: BLE001 -- one filer must not stop the batch
            failed[t] = f'{type(exc).__name__}: {exc}'[:200]
            print(f'FAIL {t}: {failed[t]}', file=sys.stderr)
            continue
        path.write_text(json.dumps(snap, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n')
        built[f'us_{t}'] = {'entity': snap['entity'], 'stock_code': snap['stock_code'], 'ticker': t, 'market': 'US',
                            'fiscal_year': snap['fiscal_year'], 'fs_div': 'CFS', 'industry': snap['pe_cr'].get('industry'),
                            'financial': snap['pe_cr'].get('industry') == 'financial', 'currency': 'USD'}
        print(f'ok   {t} {snap["entity"]} FY{snap["fiscal_year"]} {snap["pe_cr"].get("industry")} sic={snap["sic"]}', file=sys.stderr)
    idx_path = OUT_DIR / 'index_v1.json'
    doc = json.loads(idx_path.read_text()) if idx_path.exists() else {'index': {}}
    doc['index'].update(built)
    doc.update(schema='kfa_pecr_index/1', generated_at=today.isoformat(), count=len(doc['index']),
               index=dict(sorted(doc['index'].items())))
    idx_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
    print(f'{len(built)} written, {skipped} fresh, {len(failed)} failed', file=sys.stderr)
    return 0 if built or skipped or not failed else 1


if __name__ == '__main__':
    sys.exit(main())
