# Market microstructure tables — 2026-08-31

공개 상품 AUM·거래대금 기반 추정. 증권사 고객 레버리지 공시가 아님. 투자 권유 아님.

## 0. 증권사 레버리지 공시?

| 항목 | 값 |
|------|-----|
| available | False |
| note | 증권사는 종목별 고객 레버리지 비율을 공시하지 않음. 대체: LETF AUM, FreeSIS 신용·미수 집계, KRX 투자자별 매매. |
| public_proxies | krx_letf_aum, krx_letf_turnover, kofia_freesis_margin, krx_investor_flows, krx_short_interest, yahoo_hk_letf, yahoo_us_levered_inverse, binance_stock_perps, us_options_regime |

## 1. Concentration (paper: concentration matters)

| metric | value | source | quality |
|--------|------:|--------|---------|
| Conc_top2 (005930+000660) % | 48.8044 | KRX OpenAPI sto/stk_bydd_trd basDd=20260831 | observed |
| Conc_top5 % | 55.8389 | KRX OpenAPI sto/stk_bydd_trd basDd=20260831 | observed |
| Conc_top10 % | 62.3158 | KRX OpenAPI sto/stk_bydd_trd basDd=20260831 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 005380, 207940, 105560, 032830 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -355375370000 | covered_underlyings_spot | estimated |
| retail | -101771888000 | covered_underlyings_spot | estimated |
| institution | -1137087076000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 24,427,732,826,021 | 17,448,380,590.01 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260831 | observed |
| KR single-stock LETF AUM (listed) | 6,455,938,791,270 | 4,611,384,850.91 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 3,920,411,919,645 | 6,517,555,966,000 | 0.0711 | 0.8905 | None |
| 005930 | 2,535,526,871,625 | 4,647,038,997,556 | 0.0352 | 0.4766 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0127 | mid | 98.0 | 2.0 | 21.0 | -188395308000 | -354779190000 | 1.5893 |
| 005930 | 0.011699999999999999 | low | 99.5 | 0.5 | 2.6 | 86623420000 | -596180000 | 1.2897 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,281,935,725,188 | 218,415,638,534 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,381,866,707,829 | 145,165,601,377 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 50,300,664,617 | 404,939,285 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 39,374,120,785 | 199,243,840 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 49,147,222,371 | 1,148,568,925 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 14,618,175,426 | 332,358,117 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 24,302,611,664 | 321,189,042 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 78,866,691,765 | 97,123,580,518 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,514,960,404,879 | 96,013,786,155 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 889,193,054,694 | 62,011,859,237 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 41,381,179,638 | 605,409,445 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 29,563,427,824 | 123,919,455 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 16,954,061,339 | 62,362,037 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 8,967,388,084 | 124,226,952 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 21,684,153,715 | 130,432,530 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 12,823,201,452 | 4,325,383,983 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 9222769701.81 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1712280303.59 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 197266549573.4 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1409643126.15 | 0.0 | 0.3028 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.0912 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 704821563.0769231 | 561341248.2604746 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 68093760.81973736 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 2850863.3466839027 | indirect_swap |

| Crypto product | underlying | OI USD | 24h vol USD | funding | impact |
|---------------|------------|-------:|------------:|--------:|--------|
| SKHYNIXUSDT | 000660 |  |  |  | ERROR |
| SAMSUNGUSDT | 005930 |  |  |  | ERROR |
| KORUUSDT | KORU |  |  |  | ERROR |
| SOXLUSDT | SOXL |  |  |  | ERROR |
| SOXSUSDT | SOXS |  |  |  | ERROR |

## 5. Rebalancing short-gamma scenarios (TR / IR)

| ticker | R | TR_abs | IR % | band |
|--------|--:|-------:|-----:|------|
| 000660 | -0.05 | 407,814,530,318 | 6.2572 | watch |
| 000660 | -0.1 | 815,629,060,635 | 12.5143 | high |
| 000660 | 0.05 | 407,814,530,318 | 6.2572 | watch |
| 000660 | 0.0127 | 103,584,890,701 | 1.5893 | low |
| 005930 | -0.05 | 256,117,327,453 | 5.5114 | watch |
| 005930 | -0.1 | 512,234,654,906 | 11.0228 | high |
| 005930 | 0.05 | 256,117,327,453 | 5.5114 | watch |
| 005930 | 0.011699999999999999 | 59,931,454,624 | 1.2897 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 17448380590.01 | -32.89 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5795 | -72.40 | estimated |
| leverage_exposure_pct_notional | None | 0.664 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 998138.22 | 2026-08-28 | observed |
| 신용잔고 | 333379.71 | 2026-08-28 | observed |
| 신용/예탁금 % | 33.4 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -268800000000.0 | 26.09.01 | observed |
| retail | 483200000000.0 | 26.09.01 | observed |
| institution | -371000000000.0 | 26.09.01 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 0.727 | 75.34 | 2.639 |
| overseas | 26 | 0.003 | 0.28 | 0.01 |
| sector | 8 | 0.113 | 11.72 | 0.411 |
| single_stock | 16 | 0.122 | 12.66 | 0.444 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
