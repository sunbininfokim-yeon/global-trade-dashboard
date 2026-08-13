# US→KR L3 pipeline — 2026-08-08

Headline: `high:downside`
Tier B edges fired: 3
Sources: cboe_vol_indices, finra_short, cboe_spot, yahoo_spot_options_fallback, cboe_options

## Channels
- downside: high heat=7.1331 kr=['000660', '005930']
- upside: quiet heat=0.0 kr=[]
- vol_up: watch heat=1.912 kr=['000660', '005930']
- vol_down: quiet heat=0.0 kr=[]

## Hit-rate (overnight open, any driver ≤−2%)
- alert days: 95 / 246
- frac_neg alert=0.7789 vs baseline=0.4756 (lift=0.3033)
- mean alert R=-0.019675 baseline=0.006639

## Recalibration suggestions
- downside_hit_rate_mean=0.8355
- keep_downside_emphasis=True

## Regime-proxy backtest (downside overnight)
- n=244 mean=-0.028192 frac_neg=0.8402

Tier A 고정 링크 (+ Tier B corr 발견, 하향 가중). 주체 특정 없음. 하방 채널 강조. open30m_prior는 수익률 버킷 프록시.
