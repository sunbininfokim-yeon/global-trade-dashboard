# CLARITY 검색·입법 단계·메일 계약 (2026-09-20)

## 확인한 사실

운영 Supabase에 `119-hr-3633` / Digital Asset Market Clarity Act가 있으며,
`gemini-embedding-001` 벡터도 존재한다(2026-09-13 생성). `HR 3633` 실패는
식별자를 의미 유사도 검색에만 넘기던 문제다. 9월 20일 Congress.gov actions
32건과 DB의 32건을 대조했다. 이는 전체 정책 코퍼스의 완전성 확인은 아니다.

공식 근거: https://www.congress.gov/bill/119th-congress/house-bill/3633/all-actions
Congress API 계약: https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/BillEndpoint.md

CLARITY 사례:
- 하원 발의: 2025-05-29.
- 하원 Agriculture / Financial Services 위원회 보고 후 하원 본회의 통과(2025-07-17, 294–134).
- 상원 Banking, Housing, and Urban Affairs 위원회 회부·보고(보고 2026-06-01).
- 2026-09-15 상원 심의 개시 동의안의 토론 종결 표결 불성립(49–50).
- 따라서 `상원 상임위 보고 + 토론 종결 표결 부결`이며, 상원 법안 통과나 법률 제정으로 표시하지 않는다.

## 검색

`H.R. 3633`, `HR3633`, `Hr 3633`, `119-hr-3633`, `H.R.3633 (119th)`를
동일한 번호로 해석한다. `(bill_type,bill_number[,congress_number])`로 직접 조회한다.
의회 번호가 생략되면 최신 의회 순으로 여러 건을 반환하고 화면에 의회 번호를 표기한다.
정확 조회가 비어도 관계없는 의미 검색 결과로 대체하지 않는다. Gemini가 없어도 번호 검색은 된다.

`수출통제` 같은 자연어 검색은 기존 Gemini RETRIEVAL_QUERY → 1536차원 정규화 →
같은 모델의 문서 벡터를 검색하는 RPC를 유지한다. 이번 수정은 새 임베딩 비용을 발생시키지 않는다.
기존 모든 벡터가 최신 원문과 일치한다는 뜻은 아니다. 입력 변경 감지/선별 재임베딩은
별도 phase2 브랜치의 freshness migration과 backfill 옵션을 사용한다.
시맨틱 답변 캐시는 본 변경에 포함하지 않는다.

## 하나의 근거 계약

`New for anti/policy-evidence.js`를 수집기, Worker, 브라우저가 공유한다.
`GET /api/us/congress/bills/{id}`에 `lifecycle`을 추가하며 기존 응답도 유지한다.

- `origin_chamber`, `current {stage,chamber,step_id,label}`
- `steps[] {id,label,chamber,state,evidence[],required_data[]}`
- `latest_event {kind,chamber,date,text,source_url,vote}`
- `procedural_alert`, `next`, `coverage`, `note`

`observed`는 해당 단계의 직접 근거가 있다는 뜻이다. 앞 단계를 자동으로 완료 처리하지 않는다.
`unconfirmed`는 근거 미확인이며 미발생을 뜻하지 않는다. 양원 조정은 필요한 경우에만 진행한다.
상대원 통과와 양원 동일안 확정을 구분한다. 상대원이 수정 없이 통과했고 발의원 통과 근거도
있거나, 별도 동의/동일안 확정 근거가 있어야 동일안 확정으로 표시한다.
현재 전체 경로는 HR/S에 대해 제공한다. 결의안은 부분 경로임을 명시하며 대통령 단계를 추정하지 않는다.

| 단계 | 전달·확인할 데이터 | 저장 / 현재 범위 |
|---|---|---|
| 발의 | 의회·유형·번호, 발의 원, 발의일, 발의자, 공식 URL | bills |
| 위원회 회부·심사 | 원, 위원회 ID/이름, 활동명·날짜, 원문 이력 | bill_committees / bill_actions; 기존 raw 활동 날짜도 API로 제공 |
| 위원회 보고 | 처리 원, 보고일, 보고 내용, 보고서 번호·URL | 보고 action 제공; 보고서 개별 URL의 완전 수집은 후속 대상 |
| 각 원 본회의 | 통과 표결인지, 결과·날짜·roll, 찬반, 원문 | bill_votes + bill_actions; 명시된 원문 찬반만 파싱, 불참·기권 없으면 null |
| 절차 표결 | cloture / motion-to-proceed 종류·결과, 찬반, 원문 | 법안 통과와 별개 이벤트, 실패를 법안 최종 부결로 보지 않음 |
| 이견 조정·동일안 확정 | 수정안/회의보고서, 동의 이력, 상대원 무수정 통과 여부 | 근거 있는 action만 표시; 원문 버전 비교는 별도 작업 |
| 대통령 송부 | 송부일, enrolled 원문 URL | bill_actions / bill_text_versions |
| 법률 제정 | 제정일, public/private 구분, 법률 번호·공식 링크 | bills / public_laws (private law는 public_laws에 넣지 않음; 별도 복구 수정 유지 필요) |

Congress sourceSystem 0=Senate, 1/2=House, 9=Library of Congress를 따른다.
알 수 없는 원은 임의로 하원/상원으로 채우지 않는다. 표결 result null을 통과로 처리하지 않는다.
찬반은 공식 action의 명시적 숫자만 추출하며 과반수로 결과를 역산하지 않는다.
동일 날짜에 시간이 없는 action의 세부 순서는 확인되지 않을 수 있다.

## 메일 연결

수집 시 전체 이력을 먼저 판정하고 `bills.raw_source.lifecycle`에 작은 스냅샷을 저장한다.
이는 bill 업데이트와 같은 트랜잭션에서 메일 outbox가 읽을 수 있으므로,
뒤에 쓰이는 자식 action 행의 저장 시점에 의존하지 않는다.

PR #321의 `20260920020000_mailing_bill_lifecycle.sql`과 메일 템플릿이 이 계약을 사용한다.
단계가 같아도 새 절차 표결·결과·날짜가 바뀌면 이벤트를 남긴다. 같은 자료를 재수집하거나
라벨만 고쳐도 중복 알림을 만들지 않는다. 첫 canonical 스냅샷은 기준점으로만 저장해
기존 오분류 보정이 대량 알림으로 이어지지 않게 한다. 기존 다음날 06시 KST 발송 예정·
재시도·수신 설정·idempotency 경로를 유지한다. 07시 전 실제 도착 보장은 메일 제공자에 달려 있다.

메일 예: `발의: 하원 / 현재: 상원 상임위 보고 / 상원 토론 종결 표결 부결 /
근거 날짜: 2026-09-15 / 찬성 49 · 반대 50 / 다음 확인: 상원 본회의 통과` + 공식 링크.
수정된 메일 migration/template은 아직 운영 적용하지 않았다. 실제 발송은 계속 OFF다.

## 검증과 반영 순서

- 정책 단위/API 회귀검증: 16개, 실제 DB CLARITY fixture 포함.
- 빌드한 Worker를 실제 Supabase에 읽기 전용 연결: `HR 3633` 정확 조회 및 상세 lifecycle HTTP 200.
- Playwright: 실제 DB fixture를 사용하는 독립 화면에서 단계·검색 후 상세 이동 확인.
- 메일: PGlite migration 재실행/기준점/동일단계 변화/중복 방지와 HTML 검증 포함 44개, tsc 및 Worker dry-run.
- 작업 중 추가된 PR #339의 검색 4분류 변경(dbb3cde6)을 보존하고 정확 번호 결과에도 제정 여부 메타데이터를 전달한다.
- PR #339 검색/상세/수집기 수정, PR #321 메일 계약 수정으로 나누어 반영한다.
- 두 PR와 미반영 복구 브랜치의 private-law/opaque-secret/embedding-freshness 수정 통합 후 배포한다.
  특히 현 로컬 recovery 수집기를 이 오래된 PR 기반 전체 파일로 덮어쓰지 않는다.
- 운영 반영 시 메일 migration 먼저 적용 → 수집기 새 스냅샷 기준점 저장 → 사이트/메일 Worker 검증.
- 신규 UI 캐시/상세 API 캐시 버전을 올렸다. 기존 DB를 대량 갱신하지 않아도 상세 화면은 원문 이력에서 새 계약을 계산한다.

별도 운영 잔여: 기존 Resend 도메인 인증 레코드와 새 계정의 키가 달라 root 도메인
인증 전환을 조정해야 한다. 메일 발송 활성화·시험 메일·PR merge/운영 배포는 이번 검증 결과와 구분한다.
