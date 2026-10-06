# US→KR L3 pipeline — 2026-10-03

Headline: `high:downside`
Tier B edges fired: 5
Sources: cboe_vol_indices, finra_short, cboe_spot, yahoo_spot_options_fallback, cboe_options

## Channels
- downside: high heat=7.3679 kr=['000660', '005930']
- upside: watch heat=1.0335 kr=['000660', '005930']
- vol_up: quiet heat=0.0 kr=[]
- vol_down: quiet heat=0.0 kr=[]

## Hit-rate (overnight open, any driver ≤−2%)
- alert days: 94 / 248
- frac_neg alert=0.7766 vs baseline=0.4798 (lift=0.2968)
- mean alert R=-0.020294 baseline=0.007009

## Recalibration suggestions
- downside_hit_rate_mean=0.8479
- keep_downside_emphasis=True

## Regime-proxy backtest (downside overnight)
- n=259 mean=-0.028644 frac_neg=0.8456

Tier A 고정 링크 (+ Tier B corr 발견, 하향 가중). 주체 특정 없음. 하방=실제 발화한 풋 우위/갭 스트레스×KR 링크 heat. IV 변화가 없으면 거래량만으로 vol-long/vol-short를 판정하지 않음. open30m_prior는 수익률 버킷 프록시(옵션 히스토리 아님).
