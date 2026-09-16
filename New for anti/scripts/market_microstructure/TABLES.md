# Market microstructure tables — 2026-09-16

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
| Conc_top2 (005930+000660) % | 49.922 | KRX OpenAPI sto/stk_bydd_trd basDd=20260916 | observed |
| Conc_top5 % | 57.028 | KRX OpenAPI sto/stk_bydd_trd basDd=20260916 | observed |
| Conc_top10 % | 63.2566 | KRX OpenAPI sto/stk_bydd_trd basDd=20260916 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 005380, 207940, 105560, 028260 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -945393831500 | covered_underlyings_spot | estimated |
| retail | -1508372606500 | covered_underlyings_spot | estimated |
| institution | 802858560000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 23,967,743,049,190 | 17,119,816,463.71 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260916 | observed |
| KR single-stock LETF AUM (listed) | 6,338,577,789,300 | 4,527,555,563.79 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 3,937,157,136,132 | 4,946,542,682,794 | 0.0748 | 0.8511 | None |
| 005930 | 2,401,420,653,168 | 2,957,721,972,027 | 0.0311 | 0.463 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0408 | mid | 97.5 | 2.5 | 31.8 | -1069749922000 | -462010145000 | 6.8171 |
| 005930 | 0.020099999999999996 | low | 99.4 | 0.6 | 3.3 | -438622684500 | -483383686500 | 3.3029 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,227,797,921,519 | 173,617,887,976 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,446,679,879,684 | 75,229,648,817 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 51,058,970,791 | 489,402,765 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 37,125,685,603 | 119,778,545 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 40,641,389,182 | 1,493,492,065 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 12,221,938,230 | 132,931,953 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 23,962,734,047 | 1,026,115,430 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 97,668,617,076 | 117,662,865,815 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,339,396,974,464 | 50,555,518,568 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 944,504,708,884 | 37,728,874,097 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 36,981,851,295 | 263,667,860 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 26,559,310,562 | 121,465,072 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 16,009,769,846 | 17,684,120 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 7,930,299,739 | 52,560,495 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 15,678,247,719 | 107,363,615 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 14,359,490,659 | 3,074,470,801 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 9055111127.57 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1402866100.51 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 209334622228.08 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1100228923.08 | 0.0 | 0.3114 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.1432 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 550114461.5384616 | 326755694.58798045 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 29663552.462973963 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 1836477.969170572 | indirect_swap |

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
| 000660 | -0.05 | 413,249,437,028 | 8.3543 | watch |
| 000660 | -0.1 | 826,498,874,057 | 16.7086 | high |
| 000660 | 0.05 | 413,249,437,028 | 8.3543 | watch |
| 000660 | 0.0408 | 337,211,540,615 | 6.8171 | watch |
| 005930 | -0.05 | 243,013,963,449 | 8.2163 | watch |
| 005930 | -0.1 | 486,027,926,897 | 16.4325 | high |
| 005930 | 0.05 | 243,013,963,449 | 8.2163 | watch |
| 005930 | 0.020099999999999996 | 97,691,613,306 | 3.3029 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 17119816463.71 | -34.15 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5766 | -72.54 | estimated |
| leverage_exposure_pct_notional | None | 0.6459 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1053275.32 | 2026-09-15 | observed |
| 신용잔고 | 328319.61 | 2026-09-15 | observed |
| 신용/예탁금 % | 31.171 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -1672600000000.0 | 26.09.16 | observed |
| retail | -1206100000000.0 | 26.09.16 | observed |
| institution | 1225100000000.0 | 26.09.16 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 3.558 | 75.78 | 18.085 |
| overseas | 26 | 0.016 | 0.34 | 0.081 |
| sector | 8 | 0.616 | 13.12 | 3.13 |
| single_stock | 16 | 0.505 | 10.76 | 2.568 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
