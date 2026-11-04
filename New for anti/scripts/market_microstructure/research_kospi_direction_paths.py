"""KOSPI index opening/closing paths, without cost or PnL calculations."""
import argparse
import hashlib
from pathlib import Path

from option_direction_model import PUBLIC, read, write
from research_short_horizon_prediction import holm
from research_stock_open_close_direction import analyze


def cash_row_reasons(row):
    reasons=[]
    if row.get('product')!='kospi_cash':reasons.append('not_market_cash')
    if row.get('security_scope')!='stock':reasons.append('stock_only_scope_not_explicit')
    if row.get('quality')!='observed':reasons.append('not_observed')
    if not row.get('date'):reasons.append('missing_daily_date')
    buy,sell=row.get('market_total_buy_krw'),row.get('market_total_sell_krw')
    import math
    if any(v is None or not math.isfinite(v) or v<=0 for v in (buy,sell)):
        reasons.append('missing_market_gross')
    elif abs(buy-sell)>max(1e6,buy*1e-6):
        reasons.append('market_buy_sell_not_balanced')
    return reasons


def run(prices,chain,market_report):
    result=analyze(read(PUBLIC/'derivatives_board_v1.json'),prices,chain,'KOSPI')
    holm(result['comparisons'])
    block=market_report['kospi_index_levels'];days=block.get('days',[])
    if len({r['date'] for r in days})!=len(days):raise ValueError('duplicate public cash dates')
    result.update(status='retrospective_research_only',
        target_instrument='Capitalization-weighted KOSPI index',
        target_contract={'opening_up':'next open > source close','closing_up':'next close > source close',
            'direction_persists':'opening and closing on same side of source close',
            'opening_extends':'close-open direction equals open-source_close direction',
            'neutral':'flat opening/closing audited and excluded from common binary comparison',
            'decision_time':'source-day after close, historical information availability unverified'},
        cash_data_status={'public_stock_only_days':len(days),'first':block.get('date_start'),
            'last':block.get('date_end'),'scope':block.get('scope_ko'),'quality':block.get('quality'),
            'use_status':'not_included_insufficient_history_for_250_train_plus_separate_calibration',
            'private_source_status':'stock-only market scope not established in checked legacy samples; separate evidence in handoff'},
        limitations=['KOSPI index target, shared KOSPI200 option inputs; not all-stock equal-weight breadth or own options for every constituent',
            'Whole-market cash investor signals are not included; explicitly stock-scoped public history too short',
            'Naver index OHLC scope not independently reconciled with KRX; same provider series used throughout',
            'Flat start/close removed using labels only; conditional nonflat cohort, not unconditional live probability',
            '32 paired calibrated Brier comparisons Holm adjusted, all targets/candidates disclosed',
            'Historical period already explored; no live prediction/model promotion',
            'Separate heads are not a joint probability distribution; persistence is final-close position, not uninterrupted intraday trend',
            'Zero calibration slope means recent class frequency only; direction signal must remain held/neutral',
            'No cost, PnL, strategy returns or option profitability calculated'])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prices',type=Path,required=True);p.add_argument('--chain',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    market=PUBLIC/'investor_price_levels_v1.json'
    result=run(read(args.prices),read(args.chain),read(market))
    result['input_sha256']={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in
        (args.prices,args.chain,market,PUBLIC/'derivatives_board_v1.json')}
    result['implementation_sha256']={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ('research_kospi_direction_paths.py','research_stock_open_close_direction.py',
                     'research_mixed_option_activity.py','research_short_horizon_prediction.py')}
    write(args.output,result);print('wrote',args.output)
