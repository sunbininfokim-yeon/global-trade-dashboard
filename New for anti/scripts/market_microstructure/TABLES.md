# Market microstructure tables — 2026-08-20

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
| Conc_top2 (005930+000660) % | 49.8815 | KRX OpenAPI sto/stk_bydd_trd basDd=20260820 | observed |
| Conc_top5 % | 57.0611 | KRX OpenAPI sto/stk_bydd_trd basDd=20260820 | observed |
| Conc_top10 % | 63.482 | KRX OpenAPI sto/stk_bydd_trd basDd=20260820 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 005380, 373220, 207940, 028260, 012450 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | 1673292569000 | covered_underlyings_spot | estimated |
| retail | -2844551003000 | covered_underlyings_spot | estimated |
| institution | 140224232000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 25,175,602,147,420 | 17,982,572,962.44 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260820 | observed |
| KR single-stock LETF AUM (listed) | 6,899,265,688,583 | 4,928,046,920.42 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 4,057,301,775,680 | 9,109,803,915,522 | 0.0873 | 0.9124 | None |
| 005930 | 2,841,963,912,903 | 6,961,393,123,500 | 0.0381 | 0.5125 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.1273 | mid | 97.7 | 2.3 | 30.3 | -1559392852000 | 529237343000 | 11.8604 |
| 005930 | 0.0949 | low | 99.5 | 0.5 | 4.7 | -1285158151000 | 1144055226000 | 7.8305 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,344,433,525,336 | 369,047,874,821 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,425,601,992,989 | 176,713,467,853 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 56,560,228,480 | 2,483,824,868 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 40,212,796,724 | 888,991,616 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 56,618,122,624 | 3,766,629,865 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 13,387,116,495 | 302,400,100 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 27,254,160,326 | 623,631,730 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 93,233,832,706 | 241,215,972,258 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,679,490,979,453 | 154,261,103,269 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 1,006,486,298,033 | 94,460,352,169 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 51,710,146,496 | 2,000,118,366 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 33,469,910,870 | 635,024,495 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 18,679,491,963 | 318,644,888 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 9,952,589,073 | 475,593,465 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 27,134,161,606 | 437,400,740 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 15,040,335,409 | 12,327,690,879 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 9856093840.83 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1712280303.59 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 197899873712.42 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1409643126.15 | 0.0 | 0.2166 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.0609 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 704821563.0769231 | 1041574799.9317228 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 183402714.41578498 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 6418510.024385154 | indirect_swap |

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
| 000660 | -0.05 | 424,376,944,109 | 4.6585 | watch |
| 000660 | -0.1 | 848,753,888,218 | 9.3169 | watch |
| 000660 | 0.05 | 424,376,944,109 | 4.6585 | watch |
| 000660 | 0.1273 | 1,080,463,699,702 | 11.8604 | high |
| 005930 | -0.05 | 287,204,458,372 | 4.1257 | watch |
| 005930 | -0.1 | 574,408,916,744 | 8.2514 | watch |
| 005930 | 0.05 | 287,204,458,372 | 4.1257 | watch |
| 005930 | 0.0949 | 545,114,061,990 | 7.8305 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 17982572962.44 | -30.84 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5938 | -71.72 | estimated |
| leverage_exposure_pct_notional | None | 0.6905 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1053542.89 | 2026-08-20 | observed |
| 신용잔고 | 318938.95 | 2026-08-20 | observed |
| 신용/예탁금 % | 30.273 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -176000000000.0 | 26.08.21 | observed |
| retail | -1165200000000.0 | 26.08.21 | observed |
| institution | 248100000000.0 | 26.08.21 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 5.246 | 76.7 | 18.153 |
| overseas | 26 | 0.024 | 0.35 | 0.084 |
| sector | 8 | 0.596 | 8.71 | 2.061 |
| single_stock | 16 | 0.974 | 14.24 | 3.371 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
