# 2026-10-14 — Claude → Codex: 미국 관세 시뮬레이터 규칙 공식자료 대조 인수인계

**받는 쪽: Codex.** 시뮬레이터 규칙(`New for anti/policy-simulator/**`)은 Codex 작업 영역이다(T51).
Claude는 이 영역을 수정하지 않는다. 이 문서는 사용자(2026-10-14) 지시를 옮긴 것이며,
**Claude 세션은 공식 사이트에 접속할 수 없어 원문 대조를 하지 못했다.** 아래 '단서'는 전부 미검증이다.

## 1. 사용자 요청 (원문 요지)

- 세율을 임의로 넣지 않는 원칙 유지.
- 정책 이름·법적 근거·세율·HTS·대상 국가·예외·발효일·기존 관세와의 중첩 관계를 **미국 공식 자료로** 조사.
- 현재 시뮬레이터에 등록된 산업·품목·국가의 **누락되었거나 오래된** 관세 규칙을 점검.
- Federal Register, HTS Chapter 99 및 주석, CBP 시행 안내(CSMS), USTR·Commerce 원문을 대조하고 **출처와 확인일**을 기록.
- **발표된 정책과 실제 발효된 정책을 구분**하고, 연장·유예·철회·법원 명령도 확인.
- 합산 관계가 불명확하거나 적용 조건을 확인할 수 없는 규칙은 **자동 계산에서 제외하고 '확인 필요'로 표시**.
- 먼저 **기존 규칙 → 확인한 공식 규칙 → 수정할 내용** 비교표. 그 결과로 **별도 PR**. **병합·배포는 대기.**

## 2. 범위와 경계

| 구분 | 내용 |
|---|---|
| 한다 | 아래 §3 현재 규칙 전체를 공식 원문과 대조 → 비교표 → 규칙·출처·기준일·테스트 수정 PR |
| 하지 않는다 | 병합·운영 배포, DB·수집·메일·workflow 변경, 유료 AI 호출 |
| 별도 단계 | **반덤핑·상계관세**(`antidumping-catalog.mjs`, 기업별 예치율). 이번 PR에 섞지 않는다. #556·#565가 AD 근거 표시만 손봤고 세율은 바꾸지 않았다 |
| 건드리지 않는다 | 수출통제 화면·데이터(수출통제는 수출통제 모니터에서만 보인다는 사용자 지시, CLAUDE.md), `app.js`·`style.css`·`index.html`(Claude 소유) |
| PR 분리 | 이 작업은 시뮬레이터 규칙만. 정책 카드(`us_tariffs_v1.json`)와 어긋나는 점은 비교표에 적고, 카드 수정이 필요하면 별도 PR |

브랜치: `codex/us-tariff-rule-audit-20261014` (최신 main에서, 전용 워크트리). `TASKS.md`에는 **본인 행을 직접** 추가한다
(번호는 PR 작성 시점의 빈 번호 확인 — 다른 PR과 충돌하지 않도록 이 문서에서는 지정하지 않는다).

## 3. 현재 시뮬레이터의 규칙 (코드에서 그대로 추출, main `cc9974d9`)

`New for anti/policy-simulator/policy-catalog.mjs` — `POLICY_AS_OF = '2026-10-11'`.
품목 25 × 국가 29 = 725칸, 이 중 `policyOptions()`가 자동 규칙을 주는 칸은 180개
(미국 국내 공급 0% 25칸 + 외국 원산지 155칸). 나머지 545칸은 수동 입력이다.

자동 계산에서 이미 빠지는 곳: **ROW(합계), CHN, CAN, MEX** 전 품목(`missingPolicyReason`),
타이어코드(fiber)의 KHM·MYS·IDN(TRQ), HTS가 비어 있는 12개 품목(국내 공급 0%만 있음).

| 품목 (HTS) | 규칙군 | 현재 코드의 규칙 | 적용 원산지 |
|---|---|---|---|
| 전력용 변압기 (8504.23.00) | `metal_floor` | 일반관세+232 **합산 15% 하한**; 미국산 금속 조건 **합산 10% 하한** | 외국 24개국 전부 |
| 전력 케이블 (8544.60.20.00) | `metal_add` | 일반관세 3.7 + 232 25%p = **28.7**; 미국산 금속 3.7+10 = **13.7**; KOR만 KORUS 0%+25%p = 25, 0%+10%p = 10 | 외국 24개국 |
| 차단기·배전기기 (8535.21.00.00, MFN 2.7) | `ordinary` = 301 강제노동 일반 경로 | KOR·JPN·CHE **12.5 합산 하한**; EU9·TWN **10 합산 하한**; VNM·BRA·TUR·AUS·SGP·THA 2.7+12.5 = **15.2**; IND·GBR·KHM·MYS·IDN 2.7+10 = **12.7** | 외국 24개국 |
| 타이어 (4011.10.10, MFN 4) | `ordinary` | 위와 같은 구조: 12.5 / 10 / **16.5** / **14** | 외국 24개국 |
| 산업용 섬유·타이어코드 (5902.20.00.00, MFN 5.8) | `ordinary` | 12.5 / 10 / **18.3**(6개국) / **15.8**(IND·GBR) | 외국 21개국 (KHM·MYS·IDN 제외) |
| 메모리 반도체 (8542.32.00) | `memory` | **0%** ("301 강제노동 Annex (b) 예외") | 외국 24개국 전부 |
| 승용차 4종: 8703.23.01 / 8703.40.00 / 8703.60.00 / 8703.80.00 | `auto` | 일반관세+232 **합산 15%** (max(MFN 2.5, 15)) | KOR·JPN만 |
| 자동차 부품 3종: 8708.30.50 / 8708.94.50.00 / 8708.80.16 | `auto_parts` | 지정 부품 232 **조건부 합산 15%** (Note 33 (g)/(l)/(t)) | KOR·JPN만 |
| 전동화 부품·직접 정의·초고압/해저/산업용 케이블·열연강판·용접강관·OCTG·트럭 타이어·탄소섬유·아라미드·SAP | — | 자동 규칙 없음 (미국 국내 0%만) | — |

- EU9 = DEU·FRA·AUT·NLD·POL·ITA·SWE·SVK·PRT. 코드의 `floor`는 EU9·TWN=10, KOR·JPN·CHE=12.5, 그 외는 MFN+추가세(10%p 그룹: IND·GBR·KHM·MYS·IDN, 나머지 12.5%p).
- 현재 코드가 인용하는 출처(`POLICY_SOURCES`): 232 금속 2026-04-02 공고 §3·§5·Annex I-B/III/IV, 232 현행 Annex III(2026-06-01), 6월 §4 미국산 금속 85%, CBP 301 강제노동 지침(2026-07-24 시행)·국가별 Annex, 한국 자동차 232(2025-21940), 일본 자동차 232(2025-17908), USTR 중국 301.
- 사용자 입력 경로(`tariffPair`)는 `extra_duty`(별도 추가세, 기본 0)와 `manual`(직접 확인한 세율+출처 메모)을 받는다. 규칙을 지울 때는 `policyOptions()`가 `[]`을 돌려주면 이 경로로 떨어진다.
- 관련 파일: `product-verification.mjs`(품목·원산지 검증 표시), `elasticities.mjs`, 테스트 `scripts/lib/country-tariff-catalog.test.mjs`, `product-verification.test.mjs`, `simulator-default-basis.test.mjs`, `industry-company-catalog.test.mjs`, `industry-monitor.test.mjs`.

## 4. 단서 (Claude 세션의 검색 요약 — **원문 미확인**)

검색 도구의 요약이므로 틀릴 수 있고, 요약 자체가 "Annex 원문을 못 찾았다"고 밝힌 항목이 많다. 아래는 **어느 문서를 열어야 하는지**의 목록이다.
일부(Ternium 6-K 등 SEC 제출서류)는 제3자 설명이라 근거로 쓰지 말 것.

| 영역 | 열어야 할 문서 | 요약이 말한 것 | 열린 질문 |
|---|---|---|---|
| 232 금속 | [FR 2026-11314 (2026-06-04)](https://www.federalregister.gov/documents/2026/06/04/2026-11314/further-adjusting-the-tariff-regimes-for-imports-of-aluminum-steel-and-copper-into-the-united-states) · 포고 11021 (2026-04-02) · [BIS 파생품 14개 추가 의견요청 FR 2026-15961](https://public-inspection.federalregister.gov/2026-15961.pdf) | 4/6부터 금속 함량이 아닌 **전체 과세가격** 기준. 완전/주로 금속 50%, 상당 금속 함량 파생품 25%, 일부 15%, 미국산 금속 10%. 금속 중량 15% 미만 제외. 6월 개정: 95%→85%, 6/8~2027-12-31 세율, "일부 관할권" 15% 하한 | **변압기 15% 하한을 24개국 전부에 적용해도 되는가**(요약은 "일부 관할권"). 케이블 25%p가 아직 맞는가. Annex III 현행 목록. 14개 추가 파생품의 결과 |
| 301 강제노동 | [FR 2026-15181 (2026-07-28)](https://www.federalregister.gov/documents/2026/07/28/2026-15181/notice-of-actions-in-section-301-investigations-of-acts-policies-and-practices-of-various-economies) · [USTR 발표](https://ustr.gov/about/policy-offices/press-office/press-releases/2026/july/ustr-takes-action-forced-labor-section-301-investigations) · [FR 2026-11296 (6/5 제안)](https://www.federalregister.gov/documents/2026/06/05/2026-11296/notice-of-determinations-and-request-for-comments-concerning-actions-in-section-301-investigations) · 대통령 각서 2026-15274 | 60개 경제권. 10%(금지 시행·약속·부분 시행) / 12.5%(그 외). EU·대만·일본·한국·스위스는 **품목별 10% 또는 12.5%, MFN 차감형**; 일본·한국·스위스는 MFN+추가세=12.5%. 캐나다 10%(Annex I, II Part A 제외). 섬유 TRQ는 9/1부터 가능하다고 함 | **EU·대만을 차단기·타이어·섬유 전부 10%로 둔 것이 품목별로 맞는가**. 베트남·멕시코·인도·영국 등의 국가별 그룹. Annex (b) 품목 예외(메모리 8542.32.00 포함 여부). TRQ 설정 여부 |
| 232 반도체 | [FR 2026-01052 (2026-01-20)](https://www.federalregister.gov/documents/2026/01/20/2026-01052/adjusting-imports-of-semiconductors-semiconductor-manufacturing-equipment-and-their-derivative) · 포고 11002 Annex · CBP CSMS 67400472 · [FR 2026-10571 대만 협정](https://www.federalregister.gov/documents/2026/05/28/2026-10571/implementing-certain-tariff-related-elements-of-a-trade-and-security-agreement-between-the-american) · [FR 2026-16400 폴리실리콘](https://www.federalregister.gov/documents/2026/08/11/2026-16400/adjusting-imports-of-polysilicon-and-its-derivatives-into-the-united-states) | 2026-01 포고는 H200 등 **첨단 연산 칩 25%** 중심, 데이터센터·R&D 등 예외. **7/1까지 데이터센터 시장 업데이트 후 변경 가능** | **메모리 8542.32.00이 232 범위인가 아닌가**. 7/1 검토 후 변경 여부. 301 Annex (b) 예외가 실제로 이 HTS를 포함하는가 |
| 232 자동차·부품 | [한국 FR 2025-21940](https://www.federalregister.gov/documents/2025/12/04/2025-21940/implementing-certain-tariff-related-elements-of-the-us-korea-strategic-trade-and-investment-deal) · [일본 FR 2025-17389](https://www.federalregister.gov/documents/2025/09/09/2025-17389/implementing-the-united-states-japan-agreement) · [부품 포함 신청 FR 2026-05681](https://www.federalregister.gov/documents/2026/03/24/2026-05681/notice-of-the-opening-of-the-inclusions-window-for-the-section-232-automobile-parts-tariff) | 한·일 모두 "MFN+232=15%, MFN≥15%면 추가 0" — 코드와 같은 구조. 부품 포함 신청 창구가 1·4·7·10월 | 현행 HTS Chapter 99 Note 33 (g)/(l)/(t)에 코드의 3개 부품 HTS가 실제로 들어 있는가. 10월 창구 결과. 전동화 부품 처리 |
| 법원·철회 | [대법원 24-1287 Learning Resources v. Trump (2026-02-20)](https://www.supremecourt.gov/opinions/25pdf/24-1287_4gcj.pdf) · CIT [26-123](https://www.cit.uscourts.gov/sites/cit/files/26-123.pdf)·[26-94](https://www.cit.uscourts.gov/sites/cit/files/26-94.pdf)·[26-47](https://www.cit.uscourts.gov/sites/cit/files/26-47.pdf) | IEEPA는 관세 권한이 아니라고 판결. IEEPA 관세는 행정명령으로 종료, 122조 임시 관세(150일 한도) 부과, 환급은 CIT·CBP | **232·301에 대한 소송·정지·집행금지가 있는가**(요약은 찾지 못함). 122조 관세의 종료 시점과 사이 공백 |

레포 내부 참고: `New for anti/public/data/trade_policy/us_tariffs_v1.json`(as_of 2026-10-09)은
`sec122-global=expired`, `ieepa-*=struck_down/ended`, `sec232-metals=active`, `sec232-autos=active`,
`sec301-forced-labor=active`, **`sec232-other=review_required`**(목재·반도체·의약품·장비·드론)로 적어 두었다.
이것도 같은 방식으로 재확인 대상이다. 시뮬레이터 코드에는 IEEPA 기반 규칙이 없음(출처가 232·301뿐)을 Claude가 확인했다.

### 우선 의심 3건

1. **변압기 15% 하한의 국가 범위** — 코드는 외국 24개국 전부, 요약은 "일부 관할권".
2. **EU9·대만 10% 하한의 품목 범위** — 코드는 차단기·타이어·섬유 전부 10%, 요약은 "품목별 10% 또는 12.5%".
3. **메모리 반도체 0%** — 시뮬레이터는 자동 계산 0%, `us_tariffs_v1.json`은 반도체 232를 `review_required`로 둠. **같은 사안에 두 데이터의 판단이 다르다.** 어느 쪽이든 원문으로 확정하고 다른 쪽을 맞출 것.

## 5. 대조 순서와 항목별 체크리스트

우선순위: **1) 232 금속(변압기·케이블) → 2) 301 강제노동(차단기·타이어·섬유, 메모리 예외) → 3) 자동차·부품 232(한·일) → 4) 모든 규칙의 연장·유예·철회·소송 → 5) 중국·캐나다·멕시코의 자동 계산 제외 유지 여부**

각 규칙마다 아래를 원문에서 확인해 비교표에 적는다.

1. 정책 이름과 법적 근거(조항·포고/각서/공고 번호)
2. **발표일 / 발효일 / 만료일**, 상태 = 시행 중 · 발표만 됨 · 유예 · 철회 · 소송으로 정지
3. 대상 HTS(10자리 가능하면)와 서술적 범위, Annex 번호와 줄
4. 세율과 방식(추가 %p / 합산 하한 / MFN 차감형), **국가별·품목별 차이**
5. 예외·조건(함량, 미국산 금속, TRQ, USMCA, 포함 신청 결과)
6. **다른 관세와의 중첩**: MFN, 232, 301, AD/CVD, 122조 — 합산 가능한지·택일인지
7. 출처 URL과 **확인일(YYYY-MM-DD)**. 확인한 원문의 판본(FR 공고일, HTS release 이름)

### 판정 원칙 (사용자 지시)

- 원문으로 확인 → 규칙 유지 또는 수정, 출처·확인일 갱신.
- 발표됐으나 미발효 → 자동 계산에 넣지 않고 '확인 필요'(발효일을 사유에 적는다).
- 중첩·적용 조건·품목 범위를 확인할 수 없음 → **`policyOptions()`가 `[]`**, `missingPolicyReason()`에 구체적 사유. 숫자를 추정해 채우지 않는다.
- `us_tariffs_v1.json`의 `rate_ko` 문장을 숫자로 파싱해 계산에 쓰지 않는다(그 파일은 `calculation_ready=false`).

## 6. 산출물

1. **비교표 문서** (예: `docs/us-tariff-rule-audit-20261014.md`) — 열: `영역·품목·원산지` | `기존 규칙(코드)` | `확인한 공식 규칙(문서·Annex·세율·HTS·예외·발효·만료·상태)` | `수정할 내용` | `출처 URL·확인일`. §3의 모든 규칙 행을 포함하고, 확인하지 못한 행은 "미확인"으로 남긴다.
2. **수정 PR** — `policy-catalog.mjs`(규칙·`POLICY_SOURCES`·`POLICY_AS_OF`), 필요하면 `product-verification.mjs`와 `missingPolicyReason`, 테스트. 바뀐 규칙마다 테스트가 원문 기준 값을 고정해야 하며, '확인 필요'로 내린 칸은 자동 규칙이 없음을 테스트로 고정한다.
3. 기존 금액 회귀(공식 workbook benchmark)가 규칙 변경으로 깨지면 이유를 문서에 적는다.
4. `./tools/ops/handoff.sh codex "요약"`으로 **자기 파일**(`docs/ops/handoff/2026-10-xx-codex-*.md`)에 인수인계 기록.
5. **draft PR로 올리고 병합·배포는 사용자 확정 대기.**

검증 명령(`docs/country-tariff-simulator.md`):

```bash
node --test scripts/lib/country-tariff-catalog.test.mjs scripts/lib/product-verification.test.mjs scripts/lib/simulator-default-basis.test.mjs scripts/lib/industry-company-catalog.test.mjs scripts/lib/industry-monitor.test.mjs
node --test scripts/lib/*.test.mjs        # Claude가 병합 전 점검에 쓴 전체 세트
for f in "New for anti/policy-simulator/"*.mjs; do node --check "$f"; done
python3 scripts/trade_policy/preview_country_simulator.py --port 8773
```

브라우저에서 확인하지 못한 항목은 PR 본문에 그대로 "미실행"이라고 쓴다(#547·#556·#565의 방식).

## 7. Claude 세션의 한계와 현재 상태

- 이 세션의 외부 접속 정책이 `www.federalregister.gov`, `hts.usitc.gov`, `www.cbp.gov`, `ustr.gov`, `www.whitehouse.gov`, `www.govinfo.gov`, `www.bis.gov`, `content.govdelivery.com`을 403으로 막았다(2026-10-14 13:11 UTC까지 재확인). 사용자가 환경 설정에서 허용했으나 이미 열려 있던 세션에는 반영되지 않았다.
- 따라서 §4는 검색 요약 기반 단서이고 **어떤 숫자도 원문으로 확인되지 않았다.** 시뮬레이터 코드·데이터는 수정하지 않았다.
- Codex 세션에서도 위 호스트에 접속할 수 없으면, 추측으로 채우지 말고 막힌 호스트를 사용자에게 보고하고 중단한다.

## 8. Codex 시작 프롬프트 (그대로 붙여넣기)

```text
역할: 미국 관세 시뮬레이터 규칙의 공식자료 대조·수정 담당 (T51 후속).
먼저 docs/ops/handoff/2026-10-14-claude-us-tariff-audit-for-codex.md 를 끝까지 읽고,
CLAUDE.md, AGENTS.md, docs/ops/OWNERS.md, docs/country-tariff-simulator.md 를 확인해.

규칙:
- 세율 임의 입력 금지. 정책 이름·법적 근거·세율·HTS·대상 국가·예외·발효일·기존 관세와의 중첩은 미국 공식 원문(Federal Register, HTS Chapter 99와 주석, CBP CSMS, USTR, Commerce/BIS)으로만.
- 발표와 실제 발효를 구분하고 연장·유예·철회·법원 명령을 확인. 출처 URL과 확인일(YYYY-MM-DD) 기록.
- 합산 관계가 불명확하거나 조건을 확인할 수 없으면 자동 계산에서 제외(policyOptions → []) 하고 '확인 필요' 사유 표시.
- 먼저 '기존 규칙 → 확인한 공식 규칙 → 수정할 내용' 비교표(docs/)를 만들고, 그 결과로 별도 draft PR.
- 병합·운영 배포 금지(사용자 확정 대기). AD/CVD 카탈로그·수출통제·app.js/style.css/index.html 수정 금지.
- 브랜치 codex/us-tariff-rule-audit-20261014, 최신 main에서 전용 워크트리. TASKS.md 에 본인 행 추가.
- 공식 호스트에 접속이 막히면 추측하지 말고 막힌 호스트를 사용자에게 보고하고 멈춰.
- 종료 시 ./tools/ops/handoff.sh codex "요약"
```
