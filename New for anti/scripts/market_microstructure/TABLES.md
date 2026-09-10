# Market microstructure tables — 2026-09-09

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
| Conc_top2 (005930+000660) % | 50.4287 | KRX OpenAPI sto/stk_bydd_trd basDd=20260909 | observed |
| Conc_top5 % | 57.5416 | KRX OpenAPI sto/stk_bydd_trd basDd=20260909 | observed |
| Conc_top10 % | 63.6566 | KRX OpenAPI sto/stk_bydd_trd basDd=20260909 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 005380, 207940, 105560, 028260 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -699856493500 | covered_underlyings_spot | estimated |
| retail | -1644528072500 | covered_underlyings_spot | estimated |
| institution | 608141807000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 25,462,771,176,145 | 18,187,693,697.25 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260909 | observed |
| KR single-stock LETF AUM (listed) | 7,376,748,685,239 | 5,269,106,203.74 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 4,722,457,874,705 | 6,518,811,756,305 | 0.0877 | 0.9675 | None |
| 005930 | 2,654,290,810,534 | 4,436,451,989,189 | 0.0308 | 0.4813 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0351 | mid | 98.1 | 1.9 | 26.5 | -1396552768000 | 77424896000 | 5.2806 |
| 005930 | 0.0 | low | 99.5 | 0.5 | 3.6 | -247975304500 | -777281389500 | 0.0 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,772,288,145,692 | 267,447,805,631 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,653,398,356,533 | 138,062,701,771 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 60,527,918,640 | 2,207,261,740 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 46,510,538,259 | 2,854,447,697 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 56,786,693,416 | 8,699,568,440 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 14,802,858,947 | 361,500,672 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 27,565,921,015 | 591,916,636 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 90,577,442,203 | 151,171,583,680 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,577,751,017,970 | 76,980,960,278 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 943,656,252,059 | 53,906,785,163 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 42,681,317,040 | 309,609,282 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 31,552,074,304 | 235,918,920 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 18,213,534,803 | 21,107,911 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 9,668,936,320 | 24,732,457 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 18,566,710,872 | 185,557,372 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 12,200,967,166 | 4,904,514,563 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 10538212407.48 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1712280303.59 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 211127137711.07 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1409643126.15 | 0.0 | 0.3027 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.0955 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 704821563.0769231 | 560809180.969412 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 55540604.92948288 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 3657207.0883897636 | indirect_swap |

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
| 000660 | -0.05 | 490,361,275,911 | 7.5222 | watch |
| 000660 | -0.1 | 980,722,551,822 | 15.0445 | high |
| 000660 | 0.05 | 490,361,275,911 | 7.5222 | watch |
| 000660 | 0.0351 | 344,233,615,690 | 5.2806 | watch |
| 005930 | -0.05 | 267,869,274,487 | 6.0379 | watch |
| 005930 | -0.1 | 535,738,548,973 | 12.0758 | high |
| 005930 | 0.05 | 267,869,274,487 | 6.0379 | watch |
| 005930 | 0.0 | 0 | 0.0 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 18187693697.25 | -30.05 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5841 | -72.19 | estimated |
| leverage_exposure_pct_notional | None | 0.7096 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1028461.7 | 2026-09-09 | observed |
| 신용잔고 | 324092.22 | 2026-09-09 | observed |
| 신용/예탁금 % | 31.512 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -2480700000000.0 | 26.09.10 | observed |
| retail | 380200000000.0 | 26.09.10 | observed |
| institution | 433400000000.0 | 26.09.10 | observed |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
