# 인수인계 2026-11-08 — claude: 기업가치 계산기 CR · PE(LBO) · 딜 뷰

받는 쪽: 이 작업을 이어받는 세션(Claude / Codex 누구든).
목적: 계산기에서 **구조조정(CR) 대상 판단, PE/LBO 인수 평가, 딜 밸류에이션, 피어 비교**를
불러올 수 있게 한다. 사용자는 유암코(연합자산관리) CR팀 지원 준비 중이고, 실제 기업 재무
분석·피어 평가에 이 화면을 쓰려 한다.

---

## 0. 결정되지 않은 것 — 먼저 사용자에게 확인

**계산을 어디서 하나.** 계산기의 투자자/PE/딜 탭은 지금 "준비 중"이다. 원래 설계는
Codex 의 Python 엔진(`New for anti/scripts/dart/dart_kfa/`, 미병합 PR #151–#167)이 계산하고
Worker 는 표시만 하는 것(`_worker.js` `DART_VIEW_PRESETS` 위 주석). Worker 에서 같은 계산을
만들면 엔진이 두 벌이 된다.

- 추천안 (Claude): Worker(`dartBasicCardsFromFacts` 옆)에 CR·LBO 카드와 피어 비교를 지금 만들고,
  Codex 엔진이 병합되면 그 출력으로 교체한다. 교체 조건을 코드 주석에 남길 것.
- 대안: Codex 엔진 병합을 기다려 연결. 엔진 한 벌 유지, 시점 불확실.

사용자 답을 받기 전에는 구현하지 말 것.

---

## 1. 현재 상태 (main, 2026-11-08 배포)

| PR | 내용 |
|---|---|
| #171 | 금융회사 판별, 매출·FCF·순부채 차단, ROE/ROA |
| #944 | 연결(CFS)이 없으면 별도(OFS)로 대체 조회 (전 연도 CFS 가 013 일 때만) |
| #945 | 비상장 DART 공시사 목록 234개 — `tools/ops/build_dart_unlisted_filers.py` |
| #946 | `/api/dart-financials?corp_code=` (비상장), UI 검색·"비상장" 칩 |
| #953 | 금융업 업권별 카드 6종, 최신연도 가드, 영업이익 태그, 비용 부호 정규화 |

엔드포인트: `GET /api/dart-financials?symbol=<6자리>` 또는 `?corp_code=<8자리, 비상장 목록에 있는 것만>`
→ `basic_cards`, `view_presets`, `entity_policy{is_financial_entity, basis, subtype}`,
`financial_profile`, `meta{listed, fs_div, price, shares_outstanding}`.
KV 키 `fin:dart:v2:*` (24h). **응답 구조를 바꾸면 v3 로 올릴 것** — 안 올리면 배포 후 하루 동안 옛 응답이 나간다.

UI: `New for anti/calculator.js` `renderKfaResult` 가 `view_presets.views[뷰].cards` 순서대로
`basic_cards[key]` 를 그린다. 카드 이름·설명은 `KFA_CARD_META`, 사유 코드 한글화는 `KFA_REASON_KO`.
카드 객체가 지원하는 필드: `value`, `series[{year,value}]`, `quarterly[{period,value}]`,
`reason`, `definition`, `components[{label,value,unit:'money'|'percent'}]` (배열일 때만 그림 —
`debt_due_within_1y.components` 는 객체라 무시됨).

**금융회사는 basic 뷰만 나간다** (투자자/PE/딜 숨김). CR·PE·딜 카드는 일반 기업에만 붙인다.

---

## 2. 만들 것

### 2-1. 구조조정(CR) 뷰 — "살 수 있는 회사인가, 얼마가 남는가"

| 카드 키(제안) | 정의 | 데이터 |
|---|---|---|
| `cr_icr_3y` | 이자보상배율 연도별 + **3년 연속 <1 이면 한계기업 플래그** (한국은행 정의) | 영업이익 / 이자비용. 이자비용은 `ifrs-full_FinanceCosts` 가 금융원가 전체라 과대 → `ifrs-full_InterestExpense` 우선 검토, 없으면 현금흐름표 `ifrs-full_InterestPaidClassifiedAsOperatingActivities`/`...FinancingActivities` |
| `cr_capital_impairment` | 자본잠식: 자본총계 < 자본금 → 부분잠식, 자본총계 < 0 → 완전잠식, 잠식률 | `BS:ifrs-full_Equity`, `BS:ifrs-full_IssuedCapital` |
| `cr_net_debt_ebitda` | 순차입금 / EBITDA | 2-4 의 EBITDA, 차입금 태그 |
| `cr_borrowing_dependence` | 차입금의존도 = 총차입금 / 총자산 | 차입금·사채 태그 합 |
| `cr_maturity_wall` | 1년 내 만기 차입금 / (현금 + 영업현금흐름) | 단기차입금 + 유동성장기부채 + 유동성사채. **만기별 분포는 XBRL 에 없음** |
| `cr_cfo_quarterly` | 분기 영업현금흐름 추이 (이미 `cfo.quarterly` 있음 — 재사용) | |
| `cr_ccc` | 현금전환주기 DSO+DIO−DPO (기존 `ccc_days` 가 null — 채워야 함) | 매출채권·재고·매입채무 + 매출원가 `ifrs-full_CostOfSales` |
| `cr_liquidation_proxy` | 청산가치 근사: 현금 100% + 매출채권 ×a + 재고 ×b + 유형자산 ×c (할인율은 **사용자 입력**, 기본값 표시) vs 계속기업가치(EV/EBITDA × 피어 배수) | BS 자산 태그. 할인율을 숨긴 단일 숫자로 내지 말 것 |

### 2-2. PE / LBO 뷰 — "얼마에 사서, 얼마나 빌리고, 얼마에 파나"

| 카드 키(제안) | 정의 |
|---|---|
| `ebitda` | 영업이익 + `CF:ifrs-full_AdjustmentsForDepreciationExpense` + `CF:ifrs-full_AdjustmentsForAmortisationExpense` (+ 사용권자산상각 `CF:dart_AdjustmentsForDepreciationRightofuseAssets` 포함 여부를 definition 에 명시) |
| `ev`, `ev_ebitda` | 시가총액 + 순차입금 (+ 비지배지분). 비상장은 null(`not_applicable:unlisted`) |
| `fcf_to_ebitda` | (EBITDA − capex − ΔNWC − 법인세납부) / EBITDA |
| `maint_capex_burden` | capex / 감가상각 |
| `nwc_change_to_sales` | 운전자본 증감(현금흐름표 자산부채 변동) / 매출 |
| `debt_capacity` | 목표 레버리지(입력, 기본 4.0x) × EBITDA − 현재 순차입금 |

**LBO 간이 모델 (UI 계산, 입력 슬라이더)** — 기존 DCF 패널(`coDcf`) 패턴을 따를 것:
입력 = 진입 EV/EBITDA, 총차입/EBITDA, 금리, EBITDA 성장률, FCF 전환율, 보유기간, 청산 EV/EBITDA.
출력 = 연도별 부채 잔액(FCF 로 상환), 청산 시 지분가치, **IRR / MOIC**, 가치창출 분해
(EBITDA 성장 / 배수 변화 / 부채상환). 저장소 규칙 `no_price_target: true` — 목표주가가 아니라
입력값에 따른 시나리오 결과로만 표시.

### 2-3. 딜 뷰

`trading_multiples`(피어 EV/EBITDA·PER·PBR 중앙값 대비), `ev_bridge`(시총 → EV 항목별),
`qoe_flags`(일회성 의심: 기타영업수익/비용, 영업외 비중, 자산처분손익이 영업이익 대비 큰 해).
`segment` 은 P2 문서테이블 엔진(Codex, `scripts/dart/docs/P2_DART_TABLE_ADAPTER.md`) 영역 — 연결 전.

### 2-4. 피어 비교

- OpenDART `company.json` 의 `induty_code`(KSIC, 예: 롯데건설 `41112`) — **확인함, 동작.**
- 상장 3,982 + 비상장 234 개의 업종코드를 오프라인으로 한 번 받아 `dart_industry_v1.json` 으로 커밋
  (`tools/ops/build_dart_unlisted_filers.py` 처럼 키는 환경변수에서만). 호출 수 ≈ 4,200, 일 한도 20,000 내.
- 같은 KSIC 앞 3~4자리로 묶어 피어 5~10개의 핵심 지표(매출, EBITDA 마진, 순차입금/EBITDA,
  ICR, ROE, EV/EBITDA)를 표로. 피어 각각을 Worker 로 호출하면 회사당 OpenDART 호출 ~12회 →
  피어 10개면 120회. **피어 지표는 배치로 미리 계산해 정적 JSON 으로 두는 쪽을 추천.**

---

## 3. 데이터에서 실제로 부딪힌 함정 (전부 2026-11-08 실데이터로 확인)

1. **같은 계정 ID 가 재무제표마다 다른 뜻.** KB금융 `ifrs-full_InsuranceServiceResult` 가 손익
   1.3조 / 현금흐름 10.8조. → `fetchDartXbrlFacts` 가 `CIS:id`, `BS:id`, `CF:id` 키도 저장한다.
   새 카드는 `finPick(facts, ['PL:…','BS:…','CF:…'])` 로 읽을 것 (`PL` = CIS/IS 둘 다).
2. **비용 부호가 회사·연도마다 다름.** 키움증권 FY2024 이자비용 −1.09조, FY2025 +. → 비용·손실은
   `finPickAbs`. 안 하면 "수익 − 비용"이 더하기가 된다.
3. **최신연도 값이 없으면 옛 연도 값이 최신처럼 보였음.** 하나증권 FY2025 영업이익이 FY2023 의
   −3,668억으로 표시됐었다. 지금은 `point()`/`card()` 가 as-of 연도가 아니면 `missing:fy<연도>`.
   새 카드도 같은 가드를 써야 한다.
4. **태그가 회사마다 다름.** 영업이익: 일반 `dart_OperatingIncomeLoss`, 금융·일부
   `ifrs-full_ProfitLossFromOperatingActivities`. 대손: `ifrs-full_Impairment…IFRS9` /
   `ifrs-full_AdditionalAllowance…` / `dart_AdditionalImpairmentLossesOfFinancialAssets`.
   표준코드 미사용(`-표준계정코드 미사용-`) 계정은 읽을 수 없다 — 한국금융지주·NH투자증권 FY2025
   트레이딩/대손이 그래서 비어 있음.
5. **연결이 없는 회사.** 자회사 없으면 CFS 가 013. `fs_div` 는 응답 단위로 하나 — 연도별로 섞지 말 것.
6. **이자비용.** 기존 `interest_expense` 태그는 `ifrs-full_FinanceCosts`(금융원가 전체) 우선이라
   ICR 이 과소. CR 의 한계기업 판정에 쓰려면 순수 이자비용 우선으로 바꾸고 definition 에 적을 것.
7. **비상장은 가격이 없다.** EV·EV/EBITDA·PER·PBR 은 `not_applicable:unlisted`. LBO 진입가치는
   사용자 입력 배수로만.

## 4. XBRL 에 없는 것 (지어내지 말고 "재무제표에 없음"으로)

차입금 만기별 분포, 담보·선순위 구조, 약정(코버넌트), 채권단 구성, QoE 조정 내역, 경영진 사업계획,
사업부문 손익(→ P2 엔진), 은행 NIM·BIS·연체율, 보험 CSM·K-ICS, 증권 NCR·수수료 부문별 내역,
NPL 매입단가·회수율.
참고: 한국자산관리공사(캠코, corp_code 00286840)는 OpenDART 공시 0건(2020~) — 공공기관이라 ALIO 에 공시. 불러올 수 없다.

## 5. 검증 방법

로컬 wrangler 없음. 실제 `_worker.js` 를 Node 로 import 해 진짜 OpenDART 를 부르는 하네스를 썼다:
워커 파일을 스크래치패드에 `.mjs` 로 복사하고, 상대 import 경로(`scripts/`, `New for anti/`)를
워크트리로 심볼릭 링크, `env = { DART_API_KEY, ASSETS: { fetch: 로컬 public/data 파일 반환 } }` 로
`worker.fetch(new Request('https://x.test/api/dart-financials?symbol=…'))` 호출.
키는 사용자에게 받아 환경변수로만 — 파일·커밋에 남기지 말 것.

회귀 기준 (FY2025, CFS): 삼성전자 매출 333.61조 · 영업이익 43.60조 / SK하이닉스 매출 97.15조 /
롯데건설(비상장) 매출 7.91조 / 우진엔텍(OFS) 매출 448억. 금융: 연합자산관리 영업이익 4,425억,
매입 전 영업현금흐름 1,159억, 미실현 평가이익 비중 45.4% / KB금융 순이자이익 13.07조, CIR 39.4%.

CR 테스트 후보: 이자보상배율 <1 이 연속된 상장사를 `cr_icr_3y` 로 먼저 찾아 대조할 것
(한국은행 금융안정보고서의 한계기업 비중과 방향이 맞는지).

## 6. 작업 환경 메모

- 디스크가 거의 꽉 차 있다(2026-11-08 기준 여유 수 GB). 이 레포는 `.venv` 가 커밋돼 있어
  워크트리 하나가 1.4GB. **sparse checkout 으로 필요한 경로만** 체크아웃할 것:
  `git worktree add --no-checkout -b claude/<주제> .worktrees/<이름> origin/main` →
  `git sparse-checkout set --no-cone /_worker.js "/New for anti/calculator.js" "/New for anti/style.css" "/New for anti/policy-evidence.js" "/New for anti/scripts/commodity_trade/" /scripts/lib/ /scripts/lobbying/ /scripts/indonesia_policy/ "/New for anti/public/data/dart_*"` → `git checkout`. (≈4MB)
- 병합·배포는 사용자가 "배포"라고 한 뒤에만.
