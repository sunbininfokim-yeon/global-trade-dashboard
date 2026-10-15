# 시뮬레이터 운영 근거 보강 · 2026-10-15

T51 후속. 사용자 요청 2→3→4→5 순서의 구현·검증 결과입니다. 정책 수집/Supabase DB와 분리합니다. 선행 #576→#578→#580이 열려 있어 이번 PR은 #580 브랜치를 base로 사용합니다. 병합·운영 배포 승인은 포함하지 않습니다.

## 2. 법인별 AD·CVD 예치 부담

기존 한국 AD 5개 사건 계산은 유지하고 별도 AD/CVD 모델을 연결했습니다. 한국 AD 계산 사건 아래에도 추가 CVD 근거 입력이 있습니다. 원산지·품목·제도·정확한 공표 법인·통관일·제품/법인 확인이 일치해야 공표 참고율로 계산합니다. AD·CVD를 자동 합산하거나 공표 마진을 최종 관세로 바꾸지 않습니다. 금액은 소수 6자리 고정 정밀도와 BigInt로 계산해 최종 USD 센트에서 반올림합니다.

| 원산지/제품 | 법인 | 제도 | 선별 이력 | 근거 |
|---|---|---|---|---|
| 중국/PVLT 타이어 | Qingdao Transamerica Tire Industrial Co., Ltd. | AD | 59.15% | [2026-16662](https://www.govinfo.gov/content/pkg/FR-2026-08-14/html/2026-16662.htm) |
| 중국/PVLT 타이어 | Shandong Haohua Tire Co., Ltd. | AD | 78.33% | 위 공고 |
| 중국/PVLT 타이어 | Triangle Tyre Co., Ltd. | AD | 59.77% | 위 공고 |
| 베트남/PVLT 타이어 | Bridgestone Tire Manufacturing Vietnam, LLC | CVD | 0.00% | [2023-21450](https://www.govinfo.gov/content/pkg/FR-2023-09-29/html/2023-21450.htm) |
| 베트남/PVLT 타이어 | Kumho Tire (Vietnam) Co., Ltd. | CVD | 7.89% | [2021-15271](https://www.govinfo.gov/content/pkg/FR-2021-07-19/html/2021-15271.htm) |
| 베트남/PVLT 타이어 | Sailun (Vietnam) Co., Ltd. | CVD | 6.23% | 위 공고 |

중국 3개 법인은 2026-08-14 공표 참고일에 한해 자동 조회합니다. 공고의 Final Results와 Cash Deposit Requirements (1)를 대조했으며 China-wide/다른 수출자와 CVD로 확대하지 않습니다. 후속 공고의 법적 영향·CBP 지침 전수 검증은 미완료라 10/15의 현행 세율로 인증하지 않습니다.

Bridgestone은 2020 보조금률 1.34%와 2021 보조금률 0%가 함께 나옵니다. 해당 공고의 Cash Deposit Instructions가 지정한 것은 2021의 0%이며 참고일은 2023-09-29입니다. Kumho/Sailun의 명령 공표는 2021-07-19지만 예치 재개 조건은 ITC 판정 공표일입니다. [ITC 2021-15108](https://www.govinfo.gov/content/pkg/FR-2021-07-16/html/2021-15108.htm)의 7/16과 별도로 저장하고, 확인한 과거 7/16~7/19만 계산합니다. 검증 범위 종료는 법적 세율 만료일이 아닙니다. 미수록 법인·오늘 날짜에는 `unresolved`/`null`을 유지합니다.

직접 입력은 사건 A-/C-·법인·HTTPS 근거·적용 조건과 확인란이 필요하며, 결과에 독립 검증 미완료로 표시합니다. 세율·일자·법인·원산지 변경 시 기존 결과/확인을 해제합니다. 금리5%·365일·10만USD는 업계 평균이 아닌 계산 예시입니다.

## 3. 해석 보류 공고 재확인

- 일본 열연 A-588-874: [2026-20934](https://www.govinfo.gov/content/pkg/FR-2026-10-14/pdf/2026-20934.pdf) 최종표와 앞 비선정 설명의 법인/13.96% 연결 충돌을 재확인했습니다. 공식 API의 2026-01-01~10/15 목록에는 이 최종결과 외 8/28 법원 관련 공고도 있지만 다른 세그먼트의 문서를 이번 불일치 정정으로 간주하지 않았습니다.
- 한국 OCTG A-580-870: [2026-19529](https://www.govinfo.gov/content/pkg/FR-2026-09-24/html/2026-19529.htm)의 최종 마진표9.80/29.94와 cash deposit 조항 `simple-average` 연결이 여전히 불명확합니다. 평균을 임의 계산하거나 표의 마진을 예치율로 자동 승격하지 않습니다.
- 두 건의 직접 계산은 계속 보류합니다. 확인한 목록/검색에서 정정이 발견되지 않았다는 것이 정정 부존재 증명은 아닙니다. 채택 IDM·회사별 CBP 지침의 해석 확인이 남았습니다. ACCESS 파일 URL 시도는 접근 실패로 본문 검증을 주장하지 않습니다.

## 4. 공고·정정 감시

`remedy-monitor-catalog.mjs`: 한국 AD5+OCTG, 베트남 CVD1, 중국 타이어 AD/CVD4, 일본 열연/라인파이프2 = 13개 사건. 역사적으로 철회된 일본 변압기·종료된 베트남 AD·다른 가공사 사건은 감시 활성 목록에 넣지 않았습니다.

실제 네트워크 실행은 공식 FR API와 GovInfo 본문 74요청으로 13/13 완료했습니다. 2026-01-01~2026-10-15 사건 연결57건/고유문서43개입니다. 로컬 기본 샌드박스의 `fetch failed` 후 승인된 일반 네트워크 실행에서 성공했으며 HTTP403/429를 우회한 실행이 아닙니다. 완결 상태에서 `--resume` 재실행은 0요청입니다. 예치율을 자동 활성화한 문서는 없습니다.

```sh
node scripts/trade_policy/discover_antidumping_notices.mjs \
  --all-remedies \
  --state-dir /Users/yeoninair/Documents/policy-downloads/remedy-review-20261015 \
  --from 2026-01-01 --through YYYY-MM-DD \
  --snapshot 'New for anti/policy-simulator/remedy-discovery-snapshot.mjs'
```

중간 중단 뒤 **같은 기준일**에서만 `--resume`을 사용합니다. 보통 갱신 때는 `--resume`을 빼 원문 해시·메타데이터·정정 변화를 다시 확인합니다. 사건별 모든 페이지/본문이 끝나야 성공 체크포인트를 기록합니다. 403/429는 전체 실행 중단, 최소4시간 또는 더 긴 Retry-After 준수입니다. 이전 성공 자료·누락된 검색 결과를 삭제하지 않습니다. 잠금이 있으면 실행하지 않으며 상태 디렉터리에 `STOP` 파일이 있으면 시작하지 않습니다. 잠금은 PID를 조사한 후 사람이 처리합니다.

- 보존 입력/체크포인트: 위 state-dir의 `state.json`, 문서번호+SHA256 HTML. 비공개 로컬, 커밋 제외.
- 생성된 공개 검토 목록: `remedy-discovery-snapshot.mjs`. 발견/정정 대기열이며 계산 세율의 입력이 아닙니다. 기존 AD5의 이전 성공 목록도 실패 시 보존합니다.
- 국가별 UI에서 이 목록과 조회 범위를 표시합니다. 원문 버전과 검토 결과가 다르면 다시 검토 대기입니다.
- 베트남 2024POR 최종결과 예정10/22는 선별 공식 일정으로만 표시합니다. 날짜가 지나면 결과/연장 확인 필요이며 자동 완료하지 않습니다. Commerce 일정 페이지의 자동 파싱·법원 docket/CBP 감시는 미구현입니다. FR의 개시/결과/연장 공고 발견과 구분합니다.
- 4시간 간격 후속 점검은 별도 thread heartbeat로 설정하며 종전 정책 DB/임베딩 예약은 재개하지 않습니다. 실행 결과/예약 ID는 아래 인수 문서에 기록합니다.

## 5. 실제 시장·기업 입력

기존 USITC DataWeb 2025년 HS6 공급국 통계를 수치 표로 추가했습니다. 수록 상위8개국 통관가액/그 소계 내 비중입니다. 세계 수입총액과 미국 국내 판매는 `null`이므로 미국 전체 시장 비중이 아닙니다. 기존50/25/25를 실측으로 바꾸지 않았습니다. [Census 수입 평가 기준](https://www.census.gov/foreign-trade/guide/sec2.html#valuation)과 [ASM 방법론](https://www.census.gov/programs-surveys/asm/technical-documentation/methodology.html)을 대조할 때도 통관가액/총출하를 곧바로 미국 구매액으로 취급하지 않습니다.

국가 화면에 검토된 시장자료 JSON 연결을 추가했습니다. 다음 양식의 `null`과 메모를 실제 검토자료로 바꿔야 합니다. 수입 구매액으로의 관세·유통마진 등 조정, 미국 내 판매, 동일 사양·기간·통화·중복 없는 전체 포함 범위를 사용자가 확인해야 합니다. `scope_reviewed` 등은 독립 검증 증명이 아닌 사용자 확인입니다. 양식 예시는 실제 시장자료가 아닙니다.

```json
{
  "schema_version": 1,
  "product": "transformer",
  "currency": "USD",
  "valuation": "purchaser_expenditure_including_tariffs",
  "scope_reviewed": true,
  "coverage_reviewed": true,
  "coverage_note": "실제 국내판매/수입 포함 범위, 잔여국과 중복 조정 근거",
  "period": {"start": "2025-01-01", "end": "2025-12-31"},
  "rows": [
    {"country": "USA", "purchase_usd": null, "measure": "domestic_sales_in_us", "evidence": {"url": "실제 HTTPS 출처", "note": "같은 품목의 미국 내 판매/평가 기준"}},
    {"country": "KOR", "purchase_usd": null, "measure": "imports_converted_to_purchaser_expenditure", "evidence": {"url": "실제 HTTPS 출처", "note": "통관가액에서 관세 포함 구매액 변환 과정"}}
  ]
}
```

화면에서 USD를 백만USD로 변환합니다. 자료 연결 후 관세 조건은 다시 확인해야 합니다. 품목/기간/공급국/구매액을 편집하면 이전 전체 자료 연결을 무효화합니다. JSON 결과에도 출처/사용자 검토 상태를 보존하며 실측 시장 보정 완료로 승격하지 않습니다.

기업 화면도 같은 법인·제품·원산지·기간의 거래자료만 연결합니다. 가격/원가 금액은 USD, 물량은 같은 제품 단위이며 기간 고정비는 해당 제품에 배분한 값입니다. 전사 매출/영업이익으로 제품 단가·원가를 생성하지 않습니다. 양식:

```json
{
  "schema_version": 1,
  "company": "효성중공업",
  "product": "transformer",
  "origin": "KOR",
  "currency": "USD",
  "quantity_unit": "동일 사양 제품의 실제 물량 단위",
  "price_basis": "customs_value_per_unit",
  "cost_scope": "same_product_period_allocated",
  "period": {"start": "2025-01-01", "end": "2025-12-31"},
  "price": null, "quantity": null, "cost": null, "fixed_cost": null,
  "evidence": {"url": "실제 HTTPS 자료 위치", "note": "제품별 판매·원가 집계 근거; 비공개 값은 공개 PR에 첨부하지 않음"}
}
```

입력은 브라우저 안에서 처리하며 전송/자동 저장하지 않습니다. 거래자료 연결도 사용자 제공·독립 검증 미완료입니다. 물량 단위와 자료 출처를 계산 JSON에 보존합니다. 실제 미국 국내 공급과 기업별 비공개 원가 확보는 남아 있습니다.

## 검증 범위

Node 관련127개, 소유권10개, 구문·공백·preview 모듈 경로 검사. 새 고정정밀도 금액/금융비용, 0과미확인, 법인/원산지/제도/날짜, 보류 사건, 입력 확인 해제, 시장/기업 JSON 연결과 실제 mount 이벤트를 검사합니다. 실제 브라우저 렌더링·운영 배포·DB·메일·유료 AI는 실행하지 않았습니다. 이전 브라우저 보안 거부를 다른 브라우저로 우회하지 않았습니다.
