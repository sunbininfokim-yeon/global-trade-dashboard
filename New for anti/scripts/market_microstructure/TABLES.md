# Market microstructure tables — 2026-08-26

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
| Conc_top2 (005930+000660) % | 49.1335 | KRX OpenAPI sto/stk_bydd_trd basDd=20260826 | observed |
| Conc_top5 % | 56.193 | KRX OpenAPI sto/stk_bydd_trd basDd=20260826 | observed |
| Conc_top10 % | 62.6762 | KRX OpenAPI sto/stk_bydd_trd basDd=20260826 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 005380, 373220, 207940, 028260, 032830 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | 92295159000 | covered_underlyings_spot | estimated |
| retail | -1409776816500 | covered_underlyings_spot | estimated |
| institution | -262354081500 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 24,568,418,408,158 | 17,548,870,291.54 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260826 | observed |
| KR single-stock LETF AUM (listed) | 6,572,466,973,640 | 4,694,619,266.89 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 3,979,810,013,418 | 4,976,617,187,500 | 0.0985 | 0.8965 | None |
| 005930 | 2,592,656,960,222 | 5,109,878,328,250 | 0.0432 | 0.4845 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.006 | mid | 98.0 | 2.0 | 21.8 | -566850656000 | -269041880000 | 0.9988 |
| 005930 | 0.0175 | low | 99.5 | 0.5 | 3.0 | -842926160500 | 361337039000 | 1.7934 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,313,926,828,874 | 267,308,088,394 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,400,990,989,295 | 112,860,266,200 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 54,167,113,975 | 683,376,930 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 40,116,765,141 | 452,646,127 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 50,803,160,933 | 1,563,740,490 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 12,775,245,756 | 165,353,250 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 25,841,980,692 | 422,163,880 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 81,187,928,752 | 106,801,297,585 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,537,972,800,192 | 127,364,145,435 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 916,036,668,963 | 84,762,519,788 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 45,418,206,271 | 797,085,472 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 30,356,875,970 | 274,827,145 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 17,243,393,758 | 168,505,045 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 9,157,591,326 | 241,490,420 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 23,641,007,535 | 451,790,214 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 12,830,416,207 | 6,712,906,229 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 9389238533.77 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1712280303.59 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 197433018405.36 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1409643126.15 | 0.0 | 0.3966 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.0829 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 704821563.0769231 | 619514450.7943081 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 61229083.62291972 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 4279763.491052847 | indirect_swap |

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
| 000660 | -0.05 | 414,218,587,092 | 8.3233 | watch |
| 000660 | -0.1 | 828,437,174,184 | 16.6466 | high |
| 000660 | 0.05 | 414,218,587,092 | 8.3233 | watch |
| 000660 | 0.006 | 49,706,230,451 | 0.9988 | low |
| 005930 | -0.05 | 261,831,779,264 | 5.124 | watch |
| 005930 | -0.1 | 523,663,558,527 | 10.2481 | high |
| 005930 | 0.05 | 261,831,779,264 | 5.124 | watch |
| 005930 | 0.0175 | 91,641,122,742 | 1.7934 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 17548870291.54 | -32.50 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5828 | -72.25 | estimated |
| leverage_exposure_pct_notional | None | 0.6714 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 989176.53 | 2026-08-26 | observed |
| 신용잔고 | 331023.67 | 2026-08-26 | observed |
| 신용/예탁금 % | 33.465 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | 133300000000.0 | 26.08.27 | observed |
| retail | -1911600000000.0 | 26.08.27 | observed |
| institution | 183500000000.0 | 26.08.27 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 3.591 | 72.77 | 18.726 |
| overseas | 26 | 0.018 | 0.36 | 0.092 |
| sector | 8 | 0.634 | 12.84 | 3.305 |
| single_stock | 16 | 0.693 | 14.04 | 3.613 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
