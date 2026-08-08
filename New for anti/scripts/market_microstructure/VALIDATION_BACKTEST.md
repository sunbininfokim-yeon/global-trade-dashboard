# Validation backtest — 2026-08-08

## 1. Paper anchors vs engine

정량 근접(≤15%): 4개 · 방향/오더일치 포함: 8/10. 레버 AUM·2.1%는 페이퍼 시점·분모 정의 차이로 현재 엔진이 낮게 나오는 편.

| field | paper | model | Δ% | band | sim |
|-------|------:|------:|---:|------|----:|
| levered_etf_aum_usd | 26.0bn | 16.4bn | -37.08681318681318 | same_order | 62.9 |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5917 | -71.82182088403002 | diverged | 28.2 |
| leverage_exposure_pct_notional | None | 0.6871 | None | n/a | None |
| conc_top2_samsung_hynix_pct | elevated (~50% discussed) | 46.3033 | None | qualitative_match | 46.3 |
| levered_etf_aum_vs_paper_peak | 53.0bn | 16.4bn | -69.14 | reset_confirmed | None |
| soxl_path_peak | 300.0 | 300.77 | 0.26 | close | 99.7 |
| soxl_path_recent | 120.0 | 140.25 | 16.88 | same_order | 83.1 |
| koru_path_peak | 64.0 | 63.24 | -1.18 | close | 98.8 |
| koru_path_recent | 17.0 | 17.36 | 2.12 | close | 97.9 |
| kospi_drawdown_from_peak_pct | -35.0 | -31.33 | 10.48 | close | 89.5 |

## 2. US stress → KR open (Hynix / Samsung)

스트레스일 = SOXL≤-10% 또는 (MU≤−5% & SMH≤−3%). 익일 KR overnight open. 알림 프록시 = 드라이버 중 하나 ≤−2%.

### 000660
- stress n=28 · KR open frac_neg=**0.8571** (baseline 0.4711) · mean=-0.037706 (base 0.005853)
- alert fires: n=28 frac_neg=0.8571 mean=-0.037706
- high stress: n=21 frac_neg=0.8095 mean=-0.039743

### 005930
- stress n=28 · KR open frac_neg=**0.7857** (baseline 0.4008) · mean=-0.028946 (base 0.005938)
- alert fires: n=28 frac_neg=0.7857 mean=-0.028946
- high stress: n=21 frac_neg=0.7619 mean=-0.030414

## Top SOXL stress → Hynix open

| US day | SOXL | MU | KR open | alert | level |
|--------|-----:|---:|--------:|:-----:|-------|
| 2026-06-05 | -0.3051 | -0.1325 | -0.103382 | True | high |
| 2026-06-23 | -0.2306 | -0.1318 | 0.01683 | True | high |
| 2025-10-10 | -0.1901 | -0.0558 | -0.05257 | True | high |
| 2026-07-01 | -0.1843 | -0.1057 | -0.081641 | True | high |
| 2026-06-16 | -0.1699 | -0.0618 | -0.019731 | True | high |
| 2026-07-02 | -0.1658 | -0.0549 | 0.004572 | True | high |
| 2026-07-29 | -0.1602 | -0.0994 | -0.028551 | True | high |
| 2026-07-07 | -0.1509 | -0.0471 | -0.03771 | True | high |
| 2026-03-03 | -0.1488 | -0.0799 | -0.047923 | True | high |
| 2026-06-26 | -0.1465 | -0.0669 | -0.013842 | True | high |
| 2026-07-28 | -0.1452 | -0.0885 | 0.010968 | True | high |
| 2025-12-12 | -0.1451 | -0.067 | -0.063047 | True | high |

옵션 체인 히스토리 없이 수익률 프록시. 투자 권유 아님.
