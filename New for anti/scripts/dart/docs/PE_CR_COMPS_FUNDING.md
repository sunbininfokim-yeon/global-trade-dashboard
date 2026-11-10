# PE/CR 재무지표, 피어 비교와 조달 만기

`build_pe_cr()` 및 `build_pe_cr.py`가 계산한다. 기존 서비스/Worker/UI·기존 모델 결과를 덮어쓰지 않는 `pe_cr` 출력이다. DART·SEC 기본 원본 어댑터가 `PECR_` 계정을 붙이므로 이전 canonical 캐시는 원본에서 다시 생성한다. 이 PR은 라이브 데이터 수집이나 배포가 아니다.

## 카드 정의와 데이터 원천

| 카드 | 정의·필요 데이터 |
|---|---|
| `net_debt` | 리스 포함 전체 금융차입 장부액 − 사용제한 없는 현금 및 현금성자산. `reviewed_disclosures`의 완전한 차입 집계와 가용현금 필요. 순현금이면 음수. 비유동부채/총부채는 대체값 아님 |
| `debt_due_within_1y` | 확인된 12개월 이내 차입·사채·리스 **원금** 전체. DART 회사채 미상환 잔액이나 미할인 원리금 주석을 전체 원금으로 사용하지 않음 |
| `liquidity_coverage_1y` | 사용제한 없는 현금 및 현금성자산 ÷ 위 12개월 원금. 규제 LCR, 미사용 차입 한도 및 미래 CFO를 포함한 커버리지와 다름 |
| `current_ratio`, `debt_ratio` | 유동자산÷유동부채, 총부채÷총자본. 후자는 이자부 레버리지나 금융사 규제 자본비율 아님 |
| `roe`, `roa` | 지배기업 소유주 귀속 순이익÷평균 지배주주 자본, 연결 당기순이익÷평균 총자산. 기초·기말 동일 범위, 0/음수 기초·기말 분모 보류, 분기는 연환산하지 않음 |
| `operating_income`, `ebit`, `ebitda` | 영업이익은 손익계산서. EBIT는 세전이익 + 손익 이자비용 − 손익 이자수익(기타 영업외 항목은 남음). EBITDA는 기존 KFA의 영업이익 + 검증된 유형·무형 상각. 두 지표 정의를 혼용하지 않음 |
| `working_capital`, `operating_nwc`, `operating_nwc_change` | 유동자산−유동부채와, 영업 매출채권+재고−매입채무 및 그 기간 변화는 서로 다른 지표. 영업운전자본은 기존 산업 적용 정책을 따름 |
| `ccc_days` | 기존 DSO+DIO−DPO. 유통의 검토된 실제 매입액 버전은 `ccc_days_on_purchases`에 따로 제공 |
| `owner_earnings_proxy` | CFO − 별도 확인된 유지보수 현금 CapEx. **대용치**이며 정상화·필요투자 추정이 아니다. 운전자본을 CFO에서 재차감하지 않음 |
| `market_cap` | 모든 보통주 종류의 기준일 가격×자기주식 제외 주식수 합산. 거래소의 공표 시총 방법과 다를 수 있음. 비상장 기업에 임의 가격을 넣지 않음 |
| `per`, `pbr` | 보통주 시총 ÷ (지배주주 연간순이익−우선주 배당·귀속액), 보통주 시총 ÷ (지배주주 자본−우선주 장부가). 우선주가 없으면 확인된 0 입력. PER는 FY만, PBR는 연결 분기 말도 가능. 양수 분모만 |
| `ev` | 보통주 시총 + 리스 포함 순부채 + 동일 시세일 우선주 가치 + 비지배지분 장부액. 부채·비지배 장부가 사용은 정책상 근사이며, 비영업투자 및 기타 거래 조정 항목은 별도. 금융사는 비적용 |
| `ev_to_ebitda`, `ev_to_ebit`, `ev_to_sales` | 양수 EV와 양수 FY 분모. 리스 포함 EV를 사용하는 EBIT/EBITDA 배율은 이 경로에서 DART의 확인된 K-IFRS/IFRS만 허용. SEC 리스 재조정 및 TTM 자동 생성은 미지원 |

단위는 `money`(원통화 절대단위), `ratio`(ROE 0.15=15%, PER 15=15배), `days`. 시세 없이 공시-only 결과를 만들 수 있고, 가격 의존 키만 사유와 함께 비어 있다.

## 배율 및 피어 입력

- `market`: 상장 여부(`is_listed`), `entity_id`, `currency`, 시세 `as_of`, 재무정보가 공개된 `fundamentals_available_date`, `coverage="all_ordinary_share_classes"`, `classes[]`. 각 주식 종류에 `id, price, price_date, price_source, shares_out, shares_date, shares_source, currency, share_basis="outstanding_excluding_treasury"`. 주식수 날짜는 시세일 이전 120일 안, 날짜가 다르면 `corporate_actions_checked: true` 필요. 분할·소각 등은 확인자가 대조한다. 공시 이전 시세를 배율에 쓰지 않는다.
- `dart_shares`: 저장된 `stockTotqySttus` 응답 `{as_of, receipt, response}`. 위 `classes[].dart_security_type`의 정확한 `se` 행을 지정해 `distb_stock_co = istc_totqy − tesstk_co`를 대조한다. 합계행을 주식 종류로 쓰지 않는다. 주가는 별도 시세원. 미공개·이전 접수 자료로 소급 계산하지 않는다.
- EV에는 `market.preferred_equity={value, as_of, currency, source}`(없다면 확인된 0)와 검토된 `noncontrolling_value`(없다면 확인된 0)가 필요하다. `corp.accounting_basis`에는 확인된 `K-IFRS`, `IFRS`, `US-GAAP`, `K-GAAP` 중 하나를 기록한다.
- `peers`: 검토한 피어들의 기존 `kfa-pe-cr/1` 엔진 출력. 대상과 각 기업에 명시 `peer_group`을 부여한다. 업종·그룹·출처·회계기준·연결·FY 시작/종료·시세일이 일치해야 한다. 종목 자기 자신과 중복은 제외한다. PER·PBR·EV 배율·ROE·ROA·CCC의 기업별 값, 관측 수, 2개 이상일 때 중앙값을 제공한다. 그룹 자동 선정, 비상장 거래 배수, 순위·목표주가는 없다.

## 금융·캐피탈 공시 프로필

- `dart_bonds`: 저장된 OpenDART `cprndNrdmpBlce` 응답 `{receipt, as_of, fs_div, currency, scale, scope_evidence, row_selector, response}`. 원문에서 범위와 단위를 확인한 뒤 `row_selector={remndr_exprtn1,remndr_exprtn2}`의 정확한 한 행만 선택한다. 회사·접수번호·결산일 일치, 만기 구간 합계=`sm` 확인. 공시에서 `-`가 0임을 확인한 경우만 `dash_means_zero: true`. 결과는 **회사채 미상환 잔액** 별도 표이며, 전체 부채 또는 전체 1년 원금과 합치지 않는다.
- `funding`은 `kfa-funding-disclosure/1`, `entity_id`, `as_of`, `fs_div`, `currency`, `scale:1`의 검토된 묶음이다. `tables[]`는 `{id,group,side,measure,source,buckets}`; 자산/부채와 원금/미할인 원리금은 따로 보존한다. 구간 `{from_month,to_month,amount}`은 0부터 순서대로, 마지막 무기한은 `to_month:null`. 12개월 경계가 없으면 보간하지 않는다. 항목 간 중복 가능성이 있어 표 전체를 자동 합산하지 않는다.
- `funding.bonds[]`는 `{id,side,fixed_non_callable,complete_schedule,remaining_principal,annual_effective_ytm,yield_as_of,yield_source,cashflows,source}`. 각 `cashflows[]`의 `date,coupon,principal` 필요. 원금 대조 후 Macaulay=`Σ(잔존연수×현재가치)/Σ현재가치`, modified=`Macaulay/(1+연복리 YTM)`(ACT/365F). 만기 구간만으로 기간 중간값을 듀레이션이라고 부르지 않는다. 변동·콜·예상 NPL 회수의 실제 민감도 또는 기관 전체 듀레이션은 산출하지 않는다.
- `segments`는 `kfa-segment-disclosure/1`, `entity_id,as_of,period_start,fs_div,currency,scale:1,rows[]`. 각 행의 `id,name,kind`(`operating_segment` 또는 `portfolio_category`) 및 `revenue`/`profit`/`assets` 중 공시된 항목을 `{value,basis,source}`로 전달한다. 예를 들어 NPL 포트폴리오와 회계상 보고부문은 이름이 같아도 구분한다. 미공시·내부거래를 추정하거나 사업부 합산을 연결 재무제표로 대체하지 않는다.
- 표/채권/세그먼트의 `source`는 `{filing_id,table,url}`이다. 원문에서 검토한 입력만 전달한다. Gemini 후보는 자동 입력하지 않는다. 연합자산관리 등 특정 발행사의 주석 행/채권별 수익률 실측은 별도.

CLI `python3 build_pe_cr.py saved_reports.json --period annual`의 선택 입력 `market, dart_shares, peer_group, peers, funding, dart_bonds, segments`를 사용한다. 통합 함수에서는 `pe_cr_` 접두어 키워드로 전달한다. synthetic 예제와 회귀 케이스는 `tests/test_pe_cr_comps_funding.py`. 화면에서는 `pe_cr.cards`, `pe_cr.peer_comparison`, `pe_cr.disclosure_profile`을 연결하는 별도 어댑터가 필요하다.

근거: [OpenDART 주식의 총수](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020002), [OpenDART 회사채 미상환 잔액](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020006), [CFA Institute 시장 배수](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-based-valuation-price-enterprise-value-multiples), [CFA Institute 채권 듀레이션](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/yield-based-bond-duration-measures-and-properties).
