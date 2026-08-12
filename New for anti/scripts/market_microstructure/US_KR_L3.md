# US→KR L3 pipeline — 2026-08-12

Headline: `high:downside`
Tier B edges fired: 11
Sources: cboe_vol_indices, finra_short, cboe_spot, yahoo_spot_options_fallback, cboe_options

## Channels
- downside: high heat=8.5735 kr=['000660', '005930']
- upside: quiet heat=0.0 kr=[]
- vol_up: high heat=3.2952 kr=['000660', '005930']
- vol_down: watch heat=1.7868 kr=['000660', '005930']

## Hit-rate (overnight open, any driver ≤−2%)
- alert days: 96 / 247
- frac_neg alert=0.7812 vs baseline=0.4818 (lift=0.2994)
- mean alert R=-0.01958 baseline=0.006566

## Recalibration suggestions
- downside_hit_rate_mean=0.8319
- keep_downside_emphasis=True

## Regime-proxy backtest (downside overnight)
- n=248 mean=-0.027777 frac_neg=0.8387

Tier A 고정 링크 (+ Tier B corr 발견, 하향 가중). 주체 특정 없음. 하방=풋 우세 레짐×KR 링크 heat. open30m_prior는 수익률 버킷 프록시(옵션 히스토리 아님).
