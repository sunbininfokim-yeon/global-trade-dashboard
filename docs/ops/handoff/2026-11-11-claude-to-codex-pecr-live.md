# 인수인계 2026-11-11 — claude → codex: PE/CR 엔진 실데이터 검증 결과

`docs/PE_CR_ENGINE.md` 의 "배포 전 필수: 제조·반도체·조선/건설·해운·금융의 저장된 실제 공시
fixture 검증, 각 후보 account_id의 의미 검증" 을 실제 OpenDART 로 돌린 결과다.
엔진 코드(`New for anti/scripts/dart/**`)는 **건드리지 않았다** — 아래는 전부 엔진 쪽 수정 제안.

## 무엇을 했나

`tools/ops/build_kfa_pecr_snapshots.py` (Claude 소유) — 회사별로 OpenDART 를 받아
`build_pe_cr.build()` 를 그대로 호출하고 결과를
`New for anti/public/data/kfa_pecr/<corp_code>_v1.json` (+ `index_v1.json`) 으로 저장.

- 입력: `company.json`(induty_code), `fnlttSinglAcntAll` FY/Q1/H1/Q3 (최신 FY, CFS 없으면 OFS),
  전 2개년 FY (`prior_reports`), `cprndNrdmpBlce`/`entrprsBilScritsNrdmpBlce`/`srtpdPsndbtNrdmpBlce`
  (`funding.dart_instruments`), `config/pe_cr_reviewed/*.json` 중 회사·연도·기준 일치분.
- 대상 15곳 (FY2025): 삼성전자, SK하이닉스, HD한국조선해양, 한화오션, 삼성중공업, 현대건설,
  롯데건설(비상장), HMM, 팬오션, 이마트, NAVER, 두산에너빌리티, 연합자산관리(OFS), 대신에프앤아이, KB금융.
- 15곳 모두 예외 없이 `build()` 통과.

## 엔진에 고칠 것 (우선순위 순)

### 1. KSIC 64992(지주회사)를 금융으로 분류 — **오분류**
HD한국조선해양(`induty_code=64992`)이 `industry=financial` 로 떨어져 FCF·EBITDA·CCC 등
산업기업 카드가 전부 `not_applicable:financial_entity`. 64992 는 "지주회사"(비금융 지주 포함)다.
KB금융도 64992 라 코드만으로는 둘을 못 가른다. 금융지주 판별은 금융업 계정(예수부채,
보험계약부채, 순이자손익 등)의 존재나 명시 목록으로 해야 한다. SK㈜·LG·HD현대 등 비금융 지주 전부 해당.

### 2. 매입채무 태그 누락 → DPO·CCC·운전자본 15/15 결측
`config/pe_cr_inputs.json` `payables` 후보 = `ifrs-full_TradePayables`, `dart_ShortTermTradePayables`.
실제: 삼성전자·SK하이닉스 FY2024·2025 모두 **`ifrs-full_TradeAndOtherCurrentPayablesToTradeSuppliers`**
(계정명 "매입채무", 미지급금·기타지급채무는 별도 행). 좁은 매입채무라 엔진 원칙(혼합 합계 금지)에 맞는다.
반면 이마트는 `ifrs-full_TradeAndOtherCurrentPayables`("매입채무 및 기타지급채무") — 이건 계속 제외가 맞다.
결과: `dpo_days`·`ccc_days`·`nwc_change_to_sales`·`operating_nwc*` 0/15.

### 3. 회사채·CP·단기사채 미상환잔액: 행 라벨과 단위
- 실제 응답의 `remndr_exprtn1` 은 **`미상환잔액`(공백 없음)**. 엔진 기본 selector 와 테스트 fixture 는
  `미상환 잔액`. 기본값으로는 실데이터에서 행을 못 찾는다. 이 스크립트는 `row_selector` 를 명시해 우회했다.
- 실제 금액은 **원 단위**다 (연합자산관리 회사채 합계 `3,500,000,000,000` = 3.5조, 재무상태표 FVTPL
  금융부채 6.14조와 정합). `test_pe_cr_funding_instruments.py` 는 `scale=1_000_000`(백만원)을 가정한다.
  15곳 전부 재무상태표 대조로 scale=1 이 나왔다. 테스트 fixture 의 단위 가정을 실응답 기준으로 바꿀 것.
- 단위 판정 방식(스크립트): 회사채 합계 × {1,10³,10⁶} 중 재무상태표 사채(없으면 차입성 부채 합계,
  그것도 없으면 부채총계) 대비 0.001~3배에 드는 것. 후보가 1000배 간격이라 하나로 정해진다.
  BS 사채 태그는 비유동분만 잡히는 경우가 많다(현대건설 1.54조 vs 1.15조, 삼성전자 143억 vs 71억).

### 4. 손익 이자비용 태그가 거의 없음 → 이자보상배율 1/15
`interest` = `IS ifrs-full_InterestExpense` 만 허용. 국내 산업기업 대부분이 손익에 `ifrs-full_FinanceCosts`
(금융원가 총액)만 태그한다. 엔진 원칙(총금융원가 대체 금지)은 옳지만, 그러면 **한계기업 판정의 핵심인
ICR 이 사실상 안 나온다**. 주석의 이자비용을 검토 묶음으로 받는 경로(#997 Gemini 후보 → 검토 → 승격)가
CR 에서 가장 시급하다. 현재 `finance_cost_coverage` 는 11/15 (참고용으로만 표시 예정).

### 5. EBITDA 1/15 (삼성전자만 — 검토 묶음 존재)
설계대로다(D&A 는 검토 묶음으로만). 다만 순차입금/EBITDA·FCF/EBITDA·EV/EBITDA 가 전부 여기에 걸린다.
현금흐름표 조정행 `ifrs-full_AdjustmentsForDepreciationExpense` / `...AmortisationExpense` 는 15곳 대부분에
있다. 이걸 "검토 묶음" 형식으로 승격하는 기준(범위가 영업이익과 일치하는지 확인 방법)을 정해 주면
이 스크립트에서 자동 생성하지 않고 후보 목록으로만 만들겠다.

### 6. 그 외 0/15
`ebit`, `cash_flow_cash_interest_financing`(국내는 이자지급을 영업활동에 분류 — 정상일 수 있음),
`net_debt`·`debt_due_within_1y`·`dscr`·`maintenance_capex`(검토 입력 필요 — 설계대로),
`market_cap`·`per`·`pbr`·`ev*`(시장 입력을 아직 안 넘김 — Claude 쪽 TODO).

## 잘 나온 것

FCF·유형투자차감FCF 11/11(비금융), 현금흐름 3분류 15/15, 부채비율 15/15, ROA 15/15, ROE 14/15
(연합자산관리 OFS 는 지배주주지분 없음), 자본잠식률 14/15, DIO 8/15, 업종 키트 분기
(조선·건설·해운·반도체·IT하드웨어·IT서비스·기계·유통) 정상.
연합자산관리 조달 만기표: CP 1.64조(90일 2,400억, 180일 9,300억, 1년 전액), 단기사채 2,500억(90일 전액),
회사채 3.5조(1년 6,000억, 90일 구간은 원표에 없음 → `missing:exact_reported_boundary`) — 엔진 테스트 의도대로.

## 재현

```bash
DART_API_KEY=... python3 tools/ops/build_kfa_pecr_snapshots.py            # 15곳
DART_API_KEY=... python3 tools/ops/build_kfa_pecr_snapshots.py 00164830   # 한 곳
```
원본은 `--cache` (기본 `$TMPDIR/kfa_pecr_cache`) 에만 저장, 공개하지 않는다. 키는 환경변수에서만.
엔진을 고친 뒤 같은 명령으로 다시 돌리면 스냅샷이 갱신된다 (`engine_commit` 필드로 버전 확인).
