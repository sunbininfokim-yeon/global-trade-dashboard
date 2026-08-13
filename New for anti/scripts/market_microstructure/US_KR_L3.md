# US→KR L3 pipeline — 2026-08-13

Headline: `high:downside`
Tier B edges fired: 9
Sources: cboe_vol_indices, finra_short, cboe_spot, yahoo_spot_options_fallback, cboe_options

## Channels
- downside: high heat=8.7456 kr=['000660', '005930']
- upside: quiet heat=0.0 kr=[]
- vol_up: high heat=3.6872 kr=['000660', '005930']
- vol_down: watch heat=1.5054 kr=['000660', '005930']

## Hit-rate (overnight open, any driver ≤−2%)
- alert days: 95 / 247
- frac_neg alert=0.7789 vs baseline=0.4818 (lift=0.2971)
- mean alert R=-0.019767 baseline=0.006783

## Recalibration suggestions
- downside_hit_rate_mean=0.8313
- keep_downside_emphasis=True

## Regime-proxy backtest (downside overnight)
- n=247 mean=-0.027882 frac_neg=0.8381

Tier A 고정 링크 (+ Tier B corr 발견, 하향 가중). 주체 특정 없음. 하방=풋 우세 레짐×KR 링크 heat. open30m_prior는 수익률 버킷 프록시(옵션 히스토리 아님).
