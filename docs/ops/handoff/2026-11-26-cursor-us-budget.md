# Cursor → Claude: 미국 예산 운영 근거 11/26 재검토

브랜치 `cursor/usa-budget-2026-11` · 기준 main `9e3aa41c6`
사용자 11/26 요청: "미국 예산 업데이트" — 기존 구조 안에서 갱신.

## 변경 (데이터·테스트만, UI 코드 없음)

- `funding_context_review.json` → `funding_context_v1.json` 재생성: 검토 11-05→11-26, 재검토 기한 11-12→12-03,
  법률 확인일 11-26. GovInfo P.L.119-103 원문 해시 `ee98f0c0…` 일치(`--check --law-file`).
- 의회 집계(11-03 CRFB, 하원 3/12·상원 0/12)는 그대로. 11-26 Congress.gov API 재확인 결과 동일하며,
  상원은 11-20 H.R.8469 심의 동의만 발의. 이 재확인은 `procedure.note`에만 기록.
- `budget_live.test.mjs`의 검토 창 날짜를 새 기한에 맞춤. README 날짜 갱신.
- 금액 파일(`budget_live_v1.json`)은 11-26 CI가 이미 10월 MTS로 게시해 손대지 않음.

## UI 쪽 제안 (선택, Claude 소유)

1. `policy-budget/context.mjs`와 `build_funding_context.py`의 출처 호스트 허용 목록에 `www.congress.gov` 추가.
   지금은 화면 검증기가 거부하므로 공식 의회 집계를 링크로 달 수 없다. 두 곳을 같이 바꿔야 한다.
2. 부채한도 칸이 없다. Treasury DTS 표 IIIC(법정 한도·한도 적용 부채)를 별도 파일로 두는 안을 PR 본문에 적었다.
3. `annual.budget.years[2026]`은 9월 MTS 기준(적자 1.99247조)이고, 10월 MTS가 9월 실적을 고쳐 1.99257조가 됐다.
   월별 계열에는 수정이 반영됐지만 연간 결산값은 갱신되지 않는다. `annual.py` 결정 사항.

12-03 이후 또는 CR 기한(12-11) 경과 시 화면은 자동으로 "재확인 필요"로 바뀐다. 후속 CR/세출법 제정 시 재검토 필요.
