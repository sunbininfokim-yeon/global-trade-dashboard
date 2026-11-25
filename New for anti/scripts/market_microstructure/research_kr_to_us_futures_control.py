"""Sensitivity study with completed Nasdaq-100 futures hourly bars at the KRX close."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import exchange_calendars as xc

import kr_to_us_semiconductor as engine


def futures_control(path, dates):
    chart, = json.loads(path.read_text())['chart']['result']
    if chart['meta']['symbol'] != 'NQ=F' or chart['meta']['dataGranularity'] not in ('1h','60m'):
        raise ValueError('expected hourly NQ futures')
    times = pd.to_datetime(chart['timestamp'],unit='s',utc=True)
    close = pd.Series(chart['indicators']['quote'][0]['close'],index=times)
    if not times.is_unique:
        raise ValueError('duplicate NQ bar')
    # Yahoo timestamps are bar starts. Keep only complete clock-hour bars.
    close = close[(times.minute==0) & (times.second==0) & close.gt(0)]
    close.index += pd.Timedelta(hours=1)
    kr = xc.get_calendar('XKRX',start=dates.min()-pd.Timedelta(days=14),end=dates.max()+pd.Timedelta(days=3))
    ny = xc.get_calendar('XNYS',start=dates.min()-pd.Timedelta(days=14),end=dates.max()+pd.Timedelta(days=3))
    dates = dates.intersection(engine.ReviewedCalendar(kr).sessions).intersection(ny.sessions)
    previous = ny.schedule.close.shift().reindex(dates)
    opening = kr.schedule.open.reindex(dates).dt.floor('h')
    cutoff = kr.schedule.close.reindex(dates).dt.floor('h')
    frame = pd.DataFrame(index=dates)
    for name, timestamps in [('prior_us_close',previous), ('kr_open',opening), ('kr_close',cutoff)]:
        frame[name] = np.log(close.reindex(timestamps).to_numpy())
    return pd.DataFrame({'nq_overnight':frame.kr_open-frame.prior_us_close,
                         'nq_korean_session':frame.kr_close-frame.kr_open})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prices',type=Path,required=True)
    p.add_argument('--hourly',type=Path,required=True)
    p.add_argument('--through',required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    frames = engine.panel(a.prices,pd.Timestamp(a.through))
    controls = futures_control(a.hourly,frames['mu'].index)
    results = {}
    for ticker in ('sox','mu'):
        frame = frames[ticker].join(controls)
        f = engine.features(ticker)
        groups = {name:cols+list(controls) for name,cols in f.items()}
        results[ticker] = {}
        for head in ('opening','closing'):
            _, report, _ = engine.validate(frame,head,groups)
            results[ticker][head] = report
    engine.save_new(a.output,results)


if __name__=='__main__':
    main()
