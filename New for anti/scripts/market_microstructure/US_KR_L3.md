# US→KR L3 pipeline — 2026-08-17

Headline: `high:downside`
Tier B edges fired: 8
Sources: cboe_vol_indices, finra_short, cboe_spot, yahoo_spot_options_fallback, cboe_options

## Channels
- downside: high heat=6.9133 kr=['000660', '005930']
- upside: quiet heat=0.435 kr=['000660', '005930']
- vol_up: watch heat=2.1224 kr=['000660', '005930']
- vol_down: quiet heat=0.6264 kr=['000660', '005930']

## Hit-rate (overnight open, any driver ≤−2%)
- alert days: 94 / 246
- frac_neg alert=0.7766 vs baseline=0.4756 (lift=0.301)
- mean alert R=-0.019804 baseline=0.007204

## Recalibration suggestions
- downside_hit_rate_mean=0.8298
- keep_downside_emphasis=True

## Regime-proxy backtest (downside overnight)
- n=244 mean=-0.028025 frac_neg=0.8361

Tier A 고정 링크 (+ Tier B corr 발견, 하향 가중). 주체 특정 없음. 하방=풋 우세 레짐×KR 링크 heat. open30m_prior는 수익률 버킷 프록시(옵션 히스토리 아님).
