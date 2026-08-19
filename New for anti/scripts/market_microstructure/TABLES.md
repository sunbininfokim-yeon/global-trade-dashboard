# Market microstructure tables — 2026-08-18

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
| Conc_top2 (005930+000660) % | 49.1422 | KRX OpenAPI sto/stk_bydd_trd basDd=20260818 | observed |
| Conc_top5 % | 56.352 | KRX OpenAPI sto/stk_bydd_trd basDd=20260818 | observed |
| Conc_top10 % | 62.7779 | KRX OpenAPI sto/stk_bydd_trd basDd=20260818 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 005380, 373220, 207940, 032830, 028260 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | 888878281500 | covered_underlyings_spot | estimated |
| retail | -481293031500 | covered_underlyings_spot | estimated |
| institution | -375422920500 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 25,484,077,871,201 | 18,202,912,765.14 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260818 | observed |
| KR single-stock LETF AUM (listed) | 7,027,516,899,185 | 5,019,654,927.99 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 4,139,429,548,935 | 8,802,822,440,885 | 0.1029 | 0.9471 | None |
| 005930 | 2,888,087,350,250 | 6,742,432,203,720 | 0.0429 | 0.5257 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0103 | low | 98.2 | 1.8 | 29.2 | -591515772000 | 733723140000 | 1.0039 |
| 005930 | -0.0219 | low | 99.5 | 0.5 | 2.8 | 110222740500 | 155155141500 | 1.8948 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,435,250,450,206 | 442,895,627,274 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,430,995,322,804 | 186,744,035,854 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 59,027,837,321 | 3,696,992,855 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 40,531,535,593 | 1,564,192,985 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 57,305,449,292 | 4,524,989,157 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 13,567,546,972 | 610,069,536 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 27,510,440,573 | 1,330,756,580 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 75,240,966,174 | 264,493,184,652 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,719,065,345,948 | 187,566,004,163 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 1,009,208,611,355 | 87,445,406,951 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 56,410,877,285 | 4,366,006,899 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 33,228,617,313 | 472,263,070 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 18,535,687,435 | 177,840,230 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 10,443,734,919 | 344,870,374 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 26,847,632,236 | 756,582,147 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 14,346,843,759 | 8,122,069,312 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 10039309855.98 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1712280303.59 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 198083089727.57 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1409643126.15 | 0.0 | 0.2242 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.0628 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 704821563.0769231 | 1647104741.9353144 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 164660806.81928194 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 10547770.700262144 | indirect_swap |

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
| 000660 | -0.05 | 428,991,148,128 | 4.8733 | watch |
| 000660 | -0.1 | 857,982,296,257 | 9.7467 | watch |
| 000660 | 0.05 | 428,991,148,128 | 4.8733 | watch |
| 000660 | 0.0103 | 88,372,176,514 | 1.0039 | low |
| 005930 | -0.05 | 291,678,103,777 | 4.326 | watch |
| 005930 | -0.1 | 583,356,207,554 | 8.652 | watch |
| 005930 | 0.05 | 291,678,103,777 | 4.326 | watch |
| 005930 | -0.0219 | 127,755,009,454 | 1.8948 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 18202912765.14 | -29.99 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5998 | -71.44 | estimated |
| leverage_exposure_pct_notional | None | 0.7124 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1047550.58 | 2026-08-18 | observed |
| 신용잔고 | 311045.33 | 2026-08-18 | observed |
| 신용/예탁금 % | 29.693 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -3472600000000.0 | 26.08.19 | observed |
| retail | 4635700000000.0 | 26.08.19 | observed |
| institution | -1339000000000.0 | 26.08.19 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 4.999 | 77.48 | 21.629 |
| overseas | 26 | 0.021 | 0.32 | 0.091 |
| sector | 8 | 0.655 | 10.16 | 2.836 |
| single_stock | 16 | 0.777 | 12.04 | 3.36 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
