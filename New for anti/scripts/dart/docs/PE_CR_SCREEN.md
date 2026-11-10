# CR·PE 공시 진단 엔진 / UI 연결 계약

같은 공시 지표를 CR은 단기유동성·상환능력부터, PE는 수익성·현금흐름·산업경쟁력부터 읽는다. 엔진은 근거가 있는 관측과 명시 입력 시나리오만 제공한다. 종합 부실 점수, 투자 후보 추천, 법정 자본잠식·차환 실패 판정은 하지 않는다.

| 영역 | 산식·관측 | 별도 입력과 해석 한계 |
| --- | --- | --- |
| 수익성 | 영업이익률 = 영업이익 ÷ 매출; EBITDA = 영업이익 + 검증된 유형 감가상각비 + 무형자산상각비, EBITDA 마진 = EBITDA ÷ 매출 | EBITDA는 동일 기간의 검증된 상각 범위 필요. 영업적자 2년 연속, 매출원가율 3개년 연속 상승 여부를 표시. 원가율은 원가 절대액 ÷ 매출 |
| 현금흐름 | 영업(CFO)·투자(CFI)·재무(CFF)활동 순액, 3개 활동 합계와 별도 환율효과; FCF = CFO − 현금 CapEx; 좁은 영업운전자본과 CCC | CFO 음수 2년 연속. 금융사도 공시 활동 순액은 제공하되 산업기업 FCF/CCC는 넣지 않는다 |
| 상환능력 | 이자보상배율 = 영업이익 ÷ 손익상 이자비용 절대값; 실적 DSCR = CFADS ÷ (실제 상환원금 + 현금 이자지급액) | 총금융비용을 이자비용으로 대체하지 않는다. ICR 3년 연속 1배 미만, 검증된 실적 DSCR 1배 미만. DSCR은 별도 확인한 동일 기간 CFADS·원리금 필요 |
| 재무구조 | 리스 포함 순부채 ÷ EBITDA; 총부채 ÷ 총자본; 총자본 음수; 동일 범위의 납입자본 대비 지배주주 자본 부족 비율 | 납입자본 비율 = max(0, (납입자본 − 지배주주 자본) ÷ 납입자본). 현재 DART의 정확한 자본금 태그만 허용. SEC 보통주 액면금액을 대용하지 않는다 |
| 단기유동성 | 검증된 12개월 금융부채 원금, 가용현금 ÷ 그 원금, 유동부채 비중, 13주 현금계획 | 유동부채·비유동부채를 1년 원금으로 간주하지 않는다. 현금만으로 원금이 부족하다는 신호는 차환 실패가 아니다. 13주는 명시된 주별 계획만 사용 |
| 산업경쟁력 | 검토된 수주잔고/신규 수주, 가동률 = 생산실적 ÷ 생산능력, 시장점유율 = 기업 수량·매출 ÷ 동일 시장 수량·매출 | 제품·지역·포함 범위·측정 단위를 검토. 전기 대비 하락 신호는 연속된 동일 범위 연간 가동률·수주잔고 쌍이 있을 때만 |
| 지배구조 | 연간 감사의견, 최대주주 변경 내역, 특수관계자 거래/잔액 | 변형 의견만 별도 신호. 강조사항·핵심감사사항은 변형 의견이 아니고, 주주 변경만으로 분쟁을 추론하지 않는다. 특수관계자 기간 거래와 기말 잔액은 합산하지 않는다 |

### API에서 엔진까지

- `python3 build_pe_cr.py saved_reports.json --period annual` (또는 `Q1`~`Q4`). 라이브 요청·키·배포는 CLI 책임이 아니다. DART: `source:"DART"`, `entity_id`(DART 고유번호), `fiscal_year_end`, `fs_div`, `currency:"KRW"`, `filings.{FY,Q1,H1,Q3}`의 각 `{request,response}`에 `fnlttSinglAcntAll` 요청 메타데이터와 원본 응답을 넣는다. 보고서가 없어도 다른 범위로 대체하지 않는다.
- SEC: `source:"SEC"`, `entity_id`(CIK), `fiscal_year_end`, `currency:"USD"`, `fs_div:"CFS"`, `companyfacts` 원본을 넣는다. SEC CIK를 확인하고 US-GAAP 태그를 사용한다. 52/53주 달력은 `report_periods`에 각 실제 보고기간 시작/끝을 전달한다. Companyfacts만으로 주석·감사의견·지배구조를 대체하지 않는다.
- `prior_reports`: 최대 5개 이전 회계연도 입력. 각 행의 `fiscal_year_end`와 DART의 `filings` 또는 SEC의 `report_periods`(및 필요한 경우 해당 기업의 `companyfacts`)를 전달한다. 이미 정규화했다면 `history`에 canonical 묶음을 준다. 추세는 선택 기간 종료일까지 완결된 최근 3개년 슬롯, 동일 발행사·출처·연결/별도·통화·이어지는 결산기간만 본다. 연간이 안 들어왔거나 충돌하면 `unavailable`; 분기 수치·직전의 먼 연도로 메우지 않는다.
- `reviewed_disclosures`, `funding`, `peer_group`, `peers` 등은 [기존 공시·만기 계약](PE_CR_COMPS_FUNDING.md)을 유지한다. 통합 경로는 `analyze_canonical_facts(..., pe_cr_history=..., pe_cr_screen_inputs=...)`를 사용한다. CLI 최상위 결과는 PE/CR 결과이고, 통합 결과에서는 `pe_cr` 아래 동일 구조다.

### 영업·투자·재무활동 현금흐름

- `pe_cr.cash_flow_statement.activities[]`의 `card_id`가 `pe_cr.cards.cfo/cfi/cff`를 가리킨다. DART는 현금흐름표(`CF`)의 정확한 IFRS 총액 태그, SEC는 해당 US-GAAP 전체 활동 태그만 사용한다. 손익·재무상태표와 계속영업만의 소계는 대체하지 않는다. 양수는 순유입, 음수는 순유출이며 통화 절대단위와 원본/차분 근거는 카드에 보존한다.
- 연간은 사업보고서/10-K 금액, 분기는 기존 canonical의 검증된 단독 분기 금액이다. 누적만 있으면 Q2=반기−Q1, Q3=9개월−반기, Q4=연간−9개월이다. 이전 누적이 없으면 해당 활동의 분기값은 결측이다. 다른 기간·연결/별도·통화를 섞지 않는다.
- `net_activity_card_id`(CFO+CFI+CFF)는 세 값이 모두 있고 같은 보고서의 접수번호가 서로 충돌하지 않을 때만 계산하며, 환율효과를 더하지 않는다. `fx_effect_card_id`는 별도 공시값이다(SEC 매핑은 제한현금 포함 태그). 세 활동 합계는 FCF나 기초·기말 현금 차이로 이름을 바꾸지 않는다.
- `activities[].details`는 유형·무형자산 현금 취득 및 DART에서 영업/재무활동에 명시 분류된 지급이자 등 **일부 항목**이다. 원본 태그 부호 기준이므로 양수 지급액이 순유입을 뜻하지 않는다. 활동 순액과 다시 더하거나, 세부항목 합으로 순액을 대체하지 않는다. 검증은 `tests/test_pe_cr_cash_flow.py`; DART/SEC 응답형 픽스처와 [Apple FY2025 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm)를 사용한다.

### 선택 `screen_inputs` (확인된 것만 전달)

- `annual_reviewed_disclosures`: `YYYY-MM-DD` 결산일 → 이전 연도 검토 공시 묶음. 정확한 이자비용 행이 누락됐을 때 같은 기간·범위·단위의 원문 증거만 받는다. 충돌한 원본을 덮지 않는다. 당기는 `reviewed_disclosures` 사용.
- `cash_plan`: `schema_version:"kfa-cash-plan/1", entity_id, fs_div, currency, scale:1, as_of, scenario_label, opening_unrestricted_cash, minimum_cash, weeks`. `weeks`는 기준일 다음 날부터 연속 7일 단위 13개: `week_start, operating_receipts, committed_financing_draws, operating_payments, cash_taxes, cash_capex, principal_payments, cash_interest`. 금액은 원통화 절대단위의 양의 규모 또는 확인된 0. 주말 현금 = 기초 + 영업수입 + 확약 조달인출 − 영업지출 − 세금 − CapEx − 원금 − 이자. 주말 최저 현금과 최초 최소현금 미달 주를 제공하며 주중 미달은 이 자료로 알 수 없다. 미확정 차환은 넣지 않는다. 이 입력은 회사 내부 자료일 수 있으므로 승인 없이 공개 스냅샷에 게시하지 않는다.
- `industry` 및 `prior_industry`: `schema_version:"kfa-screen-industry/1", entity_id, fs_div, currency, scale:1, as_of, rows`. 각 행 `{metric,scope,unit,period_start,period_end,numerator,denominator,source}`. `metric`은 `capacity_utilization`, `market_share` 또는 `order_backlog`. 수주잔고는 `period_start:null, denominator:null` 및 원통화 절대금액; 비율의 분자·분모는 같은 단위. `scope`는 제품·지역·포함 범위·측정 기준이 동일할 때만 같은 값으로 준다. 숫자가 없으면 0 행을 만들지 않는다.
- `governance`: `schema_version:"kfa-screen-governance/1", entity_id, fs_div, currency, scale:1, as_of, period_start`. 선택 `audit:{opinion,auditor,source}` (연간, `unmodified|qualified|adverse|disclaimer`), `ownership_events:[{date,holder,source}]`, `related_party_transactions:[{category,counterparty,amount,basis,source}]`. `basis`는 `period_transaction` 또는 `closing_balance`. `source`는 검토된 원문의 `{filing_id,url,locator}`(HTTPS)다. SEC는 10-K/감사보고서·proxy·관련 공시 원문에서 확인한 항목만 입력한다.
- `dart_audit` / `dart_ownership`: 별도 OpenDART 엔드포인트 응답 `{endpoint,receipt,as_of,response}`. 전자는 `accnutAdtorNmNdAdtOpinion`(연간 `reprt_code:"11011"`, `fs_div`, `scope_evidence` 추가), 후자는 `hyslrChgSttus`. 동일 기업·접수번호와 현재 결산일의 행만 채택한다. `013`은 조회 결과 없음이지 적정/변동 없음이 아니다.

### Claude 연결

1. `unified_views.expert_diagnostics.lenses` 또는 `pe_cr.cr_pe_screen.lens_order`에서 CR/PE 표시 순서를 읽는다. 기존 Basic·재무팀·PE·IB의 탭 순서는 바꾸지 않는다.
2. `pe_cr.cr_pe_screen.sections[].card_ids`를 `pe_cr.cards`에서 렌더링한다. `ratio`는 마진/구성비/가동률/점유율/자본 부족 비율에 %, 커버리지·레버리지에 배수를 사용한다. 화면에서 산식을 다시 계산하지 않는다.
3. `signals[]`의 `triggered`는 관측 신호, `not_triggered`는 검증한 조건 미충족, `unavailable`은 근거 부족, `not_applicable`은 비적용이다. 후자의 둘을 정상/0으로 표시하지 않는다. `observations`와 `reason`을 표시한다. 13주 계획은 별도 시나리오로 표시한다. `industry_observations`와 `governance`는 원문 링크를 노출한다. 만기·피어는 기존 `disclosure_profile`·`peer_comparison`을 재사용한다.

공식 입력 문서: [OpenDART 재무제표](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020), [OpenDART 감사의견](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020009), [OpenDART 최대주주 변동](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019008), [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). 회귀 테스트는 `tests/test_pe_cr_screen.py`; 저장 응답 구조와 산식·결측·게이팅을 검증하며 라이브 또는 배포 실측을 의미하지 않는다.
