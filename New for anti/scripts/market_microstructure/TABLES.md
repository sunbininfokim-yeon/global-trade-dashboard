# Market microstructure tables — 2026-11-02

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
| Conc_top2 (005930+000660) % | 49.9279 | KRX OpenAPI sto/stk_bydd_trd basDd=20261102 | observed |
| Conc_top5 % | 57.3002 | KRX OpenAPI sto/stk_bydd_trd basDd=20261102 | observed |
| Conc_top10 % | 63.8426 | KRX OpenAPI sto/stk_bydd_trd basDd=20261102 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 207940, 005380, 105560, 032830 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -117836692000 | covered_underlyings_spot | estimated |
| retail | -792904682000 | covered_underlyings_spot | estimated |
| institution | 421028442000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 20,080,211,381,888 | 14,343,008,129.92 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20261102 | observed |
| KR single-stock LETF AUM (listed) | 4,421,839,738,270 | 3,158,456,955.91 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 2,639,417,430,210 | 3,772,550,907,797 | 0.1092 | 0.6818 | None |
| 005930 | 1,782,422,308,060 | 3,287,395,696,418 | 0.047 | 0.3804 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0381 | high | 96.7 | 3.4 | 38.5 | -378205376000 | -235977792000 | 5.6884 |
| 005930 | 0.0178 | low | 99.0 | 1.0 | 4.0 | -414699306000 | 118141100000 | 1.9698 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 1,489,559,575,002 | 179,724,170,782 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 952,298,883,283 | 71,427,557,853 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 31,542,642,371 | 532,235,459 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 24,522,691,731 | 370,347,510 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 31,224,055,739 | 786,792,231 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 7,477,180,362 | 207,062,302 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 14,387,514,768 | 206,460,774 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 88,404,886,954 | 158,588,018,950 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,076,874,105,727 | 82,991,953,163 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 611,884,587,562 | 64,670,695,681 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 29,029,511,464 | 633,892,183 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 20,099,363,442 | 42,639,007 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 9,626,408,316 | 8,576,465 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 6,102,803,419 | 31,187,402 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 10,554,891,448 | 169,603,817 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 18,250,636,682 | 6,115,175,435 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 6316913911.81 |
| HK CSOP swap LETF | notional AUM×\|L\| | None |
| Crypto Binance perps | OI notional | None |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 227718782983.81 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | None | 0.0 | None | 0.0 |
| 005930 | None | 0.0 | None | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | None | None | 764028905.3290112 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | None | None | 124010561.6014739 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | None | None | 5137144.202322864 | indirect_swap |

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
| 000660 | -0.05 | 281,622,720,412 | 7.465 | watch |
| 000660 | -0.1 | 563,245,440,824 | 14.9301 | high |
| 000660 | 0.05 | 281,622,720,412 | 7.465 | watch |
| 000660 | 0.0381 | 214,596,512,954 | 5.6884 | watch |
| 005930 | -0.05 | 181,892,358,142 | 5.533 | watch |
| 005930 | -0.1 | 363,784,716,285 | 11.066 | high |
| 005930 | 0.05 | 181,892,358,142 | 5.533 | watch |
| 005930 | 0.0178 | 64,753,679,499 | 1.9698 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 14343008129.92 | -44.83 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5537 | -73.63 | estimated |
| leverage_exposure_pct_notional | None | 0.5168 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 902351.06 | 2026-10-30 | observed |
| 신용잔고 | 290664.35 | 2026-10-30 | observed |
| 신용/예탁금 % | 32.212 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -384500000000.0 | 26.11.02 | observed |
| retail | -1330300000000.0 | 26.11.02 | observed |
| institution | 1225700000000.0 | 26.11.02 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 4.841 | 78.43 | 24.117 |
| overseas | 25 | 0.018 | 0.29 | 0.089 |
| sector | 8 | 0.751 | 12.17 | 3.743 |
| single_stock | 16 | 0.562 | 9.11 | 2.801 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
