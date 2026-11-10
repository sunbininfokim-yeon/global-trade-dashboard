# PE/CR 재무지표, 피어 비교와 조달 만기

`build_pe_cr()` 및 `build_pe_cr.py`가 계산한다. 기존 서비스/Worker/UI·기존 모델 결과를 덮어쓰지 않는 `pe_cr` 출력이다. DART·SEC 기본 원본 어댑터가 `PECR_` 계정을 붙이므로 이전 canonical 캐시는 원본에서 다시 생성한다. 이 PR은 라이브 데이터 수집이나 배포가 아니다.

## 카드 정의와 데이터 원천

| 카드 | 정의·필요 데이터 |
|---|---|
| `net_debt` | 리스 포함 전체 금융차입 장부액 − 사용제한 없는 현금 및 현금성자산. `reviewed_disclosures`의 완전한 차입 집계와 가용현금 필요. 순현금이면 음수. 비유동부채/총부채는 대체값 아님 |
| `debt_due_within_1y` | 확인된 12개월 이내 차입·사채·리스 **원금** 전체. DART 회사채 미상환 잔액이나 미할인 원리금 주석을 전체 원금으로 사용하지 않음 |
| `liquidity_coverage_1y` | 사용제한 없는 현금 및 현금성자산 ÷ 위 12개월 원금. 규제 LCR, 미사용 차입 한도 및 미래 CFO를 포함한 커버리지와 다름 |
| `current_ratio`, `debt_ratio` | 유동자산÷유동부채, 총부채÷총자본. 후자는 이자부 레버리지나 금융사 규제 자본비율 아님 |
| `current_liabilities_share` | 유동부채 ÷ 총부채. 재무상태표상 비중으로 매입채무·세금 포함 |
| `financing_principal_due_1y_share` | 동일한 완전 원금 만기표에서 12개월 내 원금 ÷ 전체 금융부채 원금. 회사채만 담긴 잔액표나 미할인 원리금은 제외 |
| `roe`, `roa` | 지배기업 소유주 귀속 순이익÷평균 지배주주 자본, 연결 당기순이익÷평균 총자산. 기초·기말 동일 범위, 0/음수 기초·기말 분모 보류, 분기는 연환산하지 않음 |
| `operating_income`, `ebit`, `ebitda` | 영업이익은 손익계산서. EBIT는 세전이익 + 손익 이자비용 − 손익 이자수익(기타 영업외 항목은 남음). EBITDA는 기존 KFA의 영업이익 + 검증된 유형·무형 상각. 두 지표 정의를 혼용하지 않음 |
| `working_capital`, `operating_nwc`, `operating_nwc_change` | 유동자산−유동부채와, 영업 매출채권+재고−매입채무 및 그 기간 변화는 서로 다른 지표. 영업운전자본은 기존 산업 적용 정책을 따름 |
| `ccc_days` | 기존 DSO+DIO−DPO. 유통의 검토된 실제 매입액 버전은 `ccc_days_on_purchases`에 따로 제공 |
| `owner_earnings_proxy` | CFO − 별도 확인된 유지보수 현금 CapEx. **대용치**이며 정상화·필요투자 추정이 아니다. 운전자본을 CFO에서 재차감하지 않음 |
| `market_cap`, `equity_market_value_total` | 보통주만의 시가총액과 우선주 포함 자기자본 시가를 분리. 자기주식 제외 기준. 검증된 제공값 또는 종목별 가격×주식수 합산; 비상장에 임의 가격을 넣지 않음 |
| `per`, `pbr` | 보통주 시총 ÷ (지배주주 연간순이익−우선주 배당·귀속액), 보통주 시총 ÷ (지배주주 자본−우선주 장부가). 우선주가 없으면 확인된 0 입력. PER는 FY만, PBR는 연결 분기 말도 가능. 양수 분모만 |
| `ev` | 보통주·우선주 합산 시가 + 리스 포함 순부채 + 비지배지분 장부액. 우선주가 제공값에 포함돼 있으면 다시 더하지 않음. 부채·비지배 장부가 사용은 정책상 근사; 비영업투자 및 기타 거래 조정은 별도. 금융사는 비적용 |
| `ev_to_ebitda`, `ev_to_ebit`, `ev_to_sales` | 양수 EV와 양수 FY 분모. 리스 포함 EV를 사용하는 EBIT/EBITDA 배율은 이 경로에서 DART의 확인된 K-IFRS/IFRS만 허용. SEC 리스 재조정 및 TTM 자동 생성은 미지원 |
| `implied_ev` | 명시 선택한 사용자 배율 또는 동기준 피어 중앙 EV/EBITDA × 대상의 양수 FY EBITDA. 시세 EV·목표주가가 아니며 기본값 없음 |

단위는 `money`(원통화 절대단위), `ratio`(ROE 0.15=15%, PER 15=15배), `days`. 시세 없이 공시-only 결과를 만들 수 있고, 가격 의존 키만 사유와 함께 비어 있다.

## 배율 및 피어 입력

- `market`: 상장 여부(`is_listed`), `entity_id`, `currency`, 시세 `as_of`, 재무정보가 공개된 `fundamentals_available_date`, `coverage="all_ordinary_share_classes"`, `classes[]`. 각 주식 종류에 `id, price, price_date, price_source, shares_out, shares_date, shares_source, currency, share_basis="outstanding_excluding_treasury"`. 주식수 날짜는 시세일 이전 120일 안, 날짜가 다르면 `corporate_actions_checked: true` 필요. 분할·소각 등은 확인자가 대조한다. 공시 이전 시세를 배율에 쓰지 않는다.
- `dart_shares`: 저장된 `stockTotqySttus` 응답 `{as_of, receipt, response}`. 위 `classes[].dart_security_type`의 정확한 `se` 행을 지정해 `distb_stock_co = istc_totqy − tesstk_co`를 대조한다. 합계행을 주식 종류로 쓰지 않는다. 주가는 별도 시세원. 미공개·이전 접수 자료로 소급 계산하지 않는다.
- 시가총액 제공값을 사용하려면 `market.classes` 대신 `market.reported_market_cap={value,as_of,currency,source,scope,scope_evidence,scale:1,share_basis:"outstanding_excluding_treasury"}`를 넣는다. `scope`는 `all_ordinary` 또는 `all_ordinary_and_preferred`만 허용한다. 종목 페이지의 숫자를 발행사 전체 값으로 간주하지 않는다. 우선주 포함 합산 시가만 확실하면 EV는 계산할 수 있지만, 우선주를 분리하기 전에는 보통주 시총·PER·PBR은 보류한다. 허용된 KRX/시장데이터 제공원, 검증된 저장 시세를 사용할 수 있다. 이 PR은 포털 크롤러나 실시간 시세 호출을 추가하지 않는다.
- 상장 우선주는 `preferred_coverage="all_preferred_share_classes"` 및 `preferred_classes[]`로 입력한다. 주가와 주식수 검증은 보통주와 같고, `dart_shares`의 우선주 `se` 행도 지원한다. 시장 시세가 없는 우선주는 별도 근거가 있는 `market.preferred_equity={value,as_of,currency,source,basis}`만 사용한다. 우선주 0은 `basis:"verified_no_preferred_outstanding"`가 필요하다. `noncontrolling_value`도 미공시를 0으로 가정하지 않는다. `corp.accounting_basis`에는 확인된 `K-IFRS`, `IFRS`, `US-GAAP`, `K-GAAP` 중 하나를 기록한다.
- `peers`: 검토한 피어들의 기존 `kfa-pe-cr/1` 엔진 출력. 대상과 각 기업에 명시 `peer_group`을 부여한다. 업종·그룹·출처·회계기준·연결·FY 시작/종료가 일치해야 한다. 시세일이 다른 경우에는 해당 행의 시장 배율만 제외하고 같은 기간의 ROE·ROA·CCC는 비교한다. 대상 기업과 중복을 제외한다. 지표별 유효 관측 2개 이상일 때 중앙값을 제공한다. 그룹 자동 선정, 비상장 거래 배수, 순위·목표주가는 없다.
- `ev_scenario`를 사용자가 지정하면 `{"method":"user_ev_ebitda_multiple","multiple":8}` 또는 `{"method":"peer_median_ev_ebitda"}`를 받는다. 후자는 같은 시세일의 유효 피어 2개 이상이 필요하다. 화면에는 `시세 기반 EV`와 `배율 시나리오 EV`로 따로 표시한다.

## 금융·캐피탈 공시 프로필

- `dart_bonds`: 저장된 OpenDART `cprndNrdmpBlce` 응답 `{receipt, as_of, fs_div, currency, scale, scope_evidence, row_selector, response}`. 원문에서 범위와 단위를 확인한 뒤 `row_selector={remndr_exprtn1,remndr_exprtn2}`의 정확한 한 행만 선택한다. 회사·접수번호·결산일 일치, 만기 구간 합계=`sm` 확인. 공시에서 `-`가 0임을 확인한 경우만 `dash_means_zero: true`. 결과는 **회사채 미상환 잔액** 별도 표이며, 전체 부채 또는 전체 1년 원금과 합치지 않는다.
- `funding`은 `kfa-funding-disclosure/1`, `entity_id`, `as_of`, `fs_div`, `currency`, `scale:1`의 검토된 묶음이다. `tables[]`는 `{id,group,side,measure,source,buckets}`; 자산/부채와 원금/미할인 원리금은 따로 보존한다. 구간 `{from_month,to_month,amount}`은 0부터 순서대로, 마지막 무기한은 `to_month:null`. 12개월 경계가 없으면 보간하지 않는다. 항목 간 중복 가능성이 있어 표 전체를 자동 합산하지 않는다.
- `funding.principal_profile={table_id,coverage:"complete_financing_principal_including_leases",source}`는 검토자가 지정한 전체 금융부채 원금표다. 12개월 경계와 끝 구간이 확인될 때만 만기 집중도를 계산한다. 별도 검토된 12개월 원금과 충돌하면 1년 만기부채·커버리지·만기 집중도를 보류한다.
- `funding.matched_gap={asset_table_id,liability_table_id,coverage:"comparable_contractual_funding_cashflows",source}`는 지정한 자산 회수·부채 상환표가 동일 범위로 비교 가능하다는 검토 근거다. 양쪽 구간 및 원금/미할인 원리금 기준이 같을 때만 `contractual_funding_gap.rows`에 구간별/누적 갭을 제공한다. NPL 예상 회수, 미확정 차환, 기초현금은 포함하지 않는다. 갭은 파산 예측이나 예상 현금잔액이 아니다.
- `funding.bonds[]`는 `{id,side,fixed_non_callable,complete_schedule,remaining_principal,annual_effective_ytm,yield_as_of,yield_source,cashflows,source}`. 각 `cashflows[]`의 `date,coupon,principal` 필요. 원금 대조 후 Macaulay=`Σ(잔존연수×현재가치)/Σ현재가치`, modified=`Macaulay/(1+연복리 YTM)`(ACT/365F). 만기 구간만으로 기간 중간값을 듀레이션이라고 부르지 않는다. 변동·콜·예상 NPL 회수의 실제 민감도 또는 기관 전체 듀레이션은 산출하지 않는다.
- `segments`는 `kfa-segment-disclosure/1`, `entity_id,as_of,period_start,fs_div,currency,scale:1,rows[]`. 각 행의 `id,name,kind`(`operating_segment` 또는 `portfolio_category`) 및 `revenue`/`profit`/`assets` 중 공시된 항목을 `{value,basis,source}`로 전달한다. 예를 들어 NPL 포트폴리오와 회계상 보고부문은 이름이 같아도 구분한다. 미공시·내부거래를 추정하거나 사업부 합산을 연결 재무제표로 대체하지 않는다.
- 표/채권/세그먼트의 `source`는 `{filing_id,table,url}`이다. 원문에서 검토한 입력만 전달한다. Gemini 후보는 자동 입력하지 않는다. 연합자산관리 등 특정 발행사의 주석 행/채권별 수익률 실측은 별도.

## Claude UI 연결 계약

1. 기업 선택 아래에 `경쟁사 추가` 검색을 놓는다. 검색은 기존 회사 검색에 연결하고 선택한 이름/티커를 서버에서 DART 기업 ID 또는 SEC CIK로 해석한다. `peer_ids`에는 선택 순서대로 최대 8개 고유 ID만 전달한다. 서버가 검증된 엔진 스냅샷을 준비한다. 클라이언트가 준 배율을 피어 데이터로 사용하지 않는다.
2. `peer_comparison.columns`와 `target.cells` 및 `included[].cells`를 렌더링한다. `excluded`에는 이름 대신 ID와 사유를 보여줄 수 있다. 각 결측의 `reason`과 지표별 `summary.count`를 표시한다. `display`가 `percent`면 소수×100, `multiple`이면 배수, `days`면 일 단위. 기업명은 텍스트로 처리한다.
3. 만기표에서 자료 기준을 고른다. 금융사는 회수 예정/상환 예정/갭을, 제조는 차입·회사채·리스 표와 `current_liabilities_share` 및 `financing_principal_due_1y_share`를 우선 표시한다. 같은 자료의 전체표·하위표를 합산하지 않는다. `implied_ev`는 사용자 선택 후에만 렌더링한다.

CLI `python3 build_pe_cr.py saved_reports.json --period annual`의 선택 입력 `market, dart_shares, peer_group, peers, peer_ids, funding, dart_bonds, segments, ev_scenario`를 사용한다. 통합 함수에서는 `pe_cr_` 접두어 키워드로 전달한다. 합성 예제와 회귀 케이스는 `tests/test_pe_cr_comps_funding.py`. Worker/UI·공개 시세 수집·특정 회사 주석의 서비스 연결은 이 PR에 없다.

근거: [OpenDART 주식의 총수](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020002), [OpenDART 회사채 미상환 잔액](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020006), [CFA Institute 시장 배수](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-based-valuation-price-enterprise-value-multiples), [CFA Institute 채권 듀레이션](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/yield-based-bond-duration-measures-and-properties).
