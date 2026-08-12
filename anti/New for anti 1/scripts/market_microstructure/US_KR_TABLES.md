# US→KR cross-market — 2026-08-08

공개·지연 데이터. 투자 권유 아님. 주체 특정 아님.

Sources: cboe_vol_indices, finra_short, cboe_spot, yahoo_spot_options_fallback, cboe_options

## Headline: `high:downside`

고정 링크 그래프 × US 레짐 점수. 주체 특정 없음. 하방 채널 강조. 임계값은 월간 재캘리브 대상.

## Channels

| channel | level | heat | KR tickers |
|---------|-------|-----:|------------|
| downside | high | 3.5625 | 000660, 005930 |
| upside | quiet | 0.0 |  |
| vol_up | watch | 1.16 | 000660, 005930 |
| vol_down | quiet | 0.0 |  |

## US names (regime)

| symbol | primary | level | regimes | P/C vol | day_R | short_chg% |
|--------|---------|-------|---------|--------:|------:|-----------:|
| MU | vol_up | quiet | vol_long_straddle | 0.7945 | 0.002769 | 14.342 |
| NVDA | quiet | quiet | quiet | 0.5061 | -0.000714 | 4.49 |
| SOXL | downside | watch | downside_put_bid | 2.1806 | 0.0 | 9.148 |
| SMH | downside | watch | downside_put_bid | 4.3901 | 0.000686 | -5.904 |

## Top transmission edges

| heat | channel | US→KR | type | regimes |
|-----:|---------|-------|------|---------|
| 1.4062 | downside | SOXL→000660 | etf_beta | downside_put_bid |
| 1.125 | downside | SOXL→005930 | etf_beta | downside_put_bid |
| 1.0312 | downside | SMH→000660 | etf_beta | downside_put_bid |
| 0.72 | vol_up | MU→000660 | peer_memory | vol_long_straddle |
| 0.44 | vol_up | MU→005930 | peer_memory | vol_long_straddle |

## Cboe vol indices

| index | as_of | close | day_R |
|-------|-------|------:|------:|
| VIX | 08/07/2026 | 14.9 | -0.016502 |
| VVIX | 08/07/2026 | 90.42 | 0.019161 |
| SKEW | 08/07/2026 | 132.57 | -0.016032 |
