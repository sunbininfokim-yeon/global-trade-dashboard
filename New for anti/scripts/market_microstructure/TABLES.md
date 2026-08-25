# Market microstructure tables — 2026-08-24

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
| Conc_top2 (005930+000660) % | 49.2842 | KRX OpenAPI sto/stk_bydd_trd basDd=20260824 | observed |
| Conc_top5 % | 56.3839 | KRX OpenAPI sto/stk_bydd_trd basDd=20260824 | observed |
| Conc_top10 % | 62.8858 | KRX OpenAPI sto/stk_bydd_trd basDd=20260824 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 005380, 373220, 207940, 028260, 105560 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -3294837218000 | covered_underlyings_spot | estimated |
| retail | 3595108042000 | covered_underlyings_spot | estimated |
| institution | -1900825768000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 24,260,690,040,004 | 17,329,064,314.29 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260824 | observed |
| KR single-stock LETF AUM (listed) | 6,449,473,920,266 | 4,606,767,085.90 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 3,951,113,416,532 | 6,858,026,942,000 | 0.0744 | 0.8991 | None |
| 005930 | 2,498,360,503,734 | 8,456,072,427,750 | 0.0338 | 0.4751 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.0341 | mid | 97.8 | 2.2 | 20.8 | 735853257000 | -1526065815000 | 4.1034 |
| 005930 | -0.087 | low | 99.4 | 0.6 | 3.9 | 2859254785000 | -1768771403000 | 5.201 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,285,879,690,512 | 288,433,228,308 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,394,705,631,685 | 111,397,185,478 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 53,570,631,289 | 1,117,956,812 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 39,378,053,080 | 469,060,919 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 51,088,410,817 | 1,712,090,528 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 12,957,840,282 | 248,155,744 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 25,930,127,149 | 637,083,766 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 87,603,031,718 | 106,278,586,720 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,476,710,297,013 | 162,634,573,703 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 884,091,506,035 | 109,207,629,984 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 44,375,706,961 | 848,742,622 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 29,831,770,132 | 397,279,322 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 16,622,805,717 | 428,537,852 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 8,759,591,256 | 307,601,370 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 23,344,294,292 | 512,021,215 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 14,624,532,328 | 11,189,795,262 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 9213534171.81 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1712280303.59 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 197257314043.4 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1409643126.15 | 0.0 | 0.2878 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.0501 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 704821563.0769231 | 770654143.452571 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 121483516.85854594 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 4473134.506365428 | indirect_swap |

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
| 000660 | -0.05 | 412,631,947,997 | 6.0168 | watch |
| 000660 | -0.1 | 825,263,895,994 | 12.0335 | high |
| 000660 | 0.05 | 412,631,947,997 | 6.0168 | watch |
| 000660 | -0.0341 | 281,414,988,534 | 4.1034 | watch |
| 005930 | -0.05 | 252,760,956,839 | 2.9891 | low |
| 005930 | -0.1 | 505,521,913,678 | 5.9782 | watch |
| 005930 | 0.05 | 252,760,956,839 | 2.9891 | low |
| 005930 | -0.087 | 439,804,064,900 | 5.201 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 17329064314.29 | -33.35 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5854 | -72.12 | estimated |
| leverage_exposure_pct_notional | None | 0.6681 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1030136.54 | 2026-08-24 | observed |
| 신용잔고 | 326282.46 | 2026-08-24 | observed |
| 신용/예탁금 % | 31.674 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -3814000000000.0 | 26.08.25 | observed |
| retail | 1050900000000.0 | 26.08.25 | observed |
| institution | 1171100000000.0 | 26.08.25 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 4.85 | 76.69 | 20.139 |
| overseas | 26 | 0.038 | 0.61 | 0.159 |
| sector | 8 | 0.594 | 9.39 | 2.466 |
| single_stock | 16 | 0.842 | 13.31 | 3.494 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
