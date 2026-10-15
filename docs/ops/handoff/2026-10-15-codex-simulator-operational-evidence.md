# T51 · AD/CVD 계산·검토 대기열·관측 입력

- Checkout: `/Users/yeoninair/Documents/country-tariff-simulator-20261011`
- Branch: `codex/simulator-operational-evidence-20261015`
- Base: `3d6a6bd9bb50ed7a7c1198b1c562ead9e40b4296` / open draft #580. 선행 #576→#578→#580은 확인 당시 모두 open draft.
- Code/data/docs commit: `e7a714d0`.
- 범위/JSON 양식/공식 출처: [구현 문서](../../simulator-operational-evidence-20261015.md).

## 실제 수행

1. AD·CVD 별도 예치/금융비용 계산, 정확한 법인/제도/원산지/품목/날짜 격리. 새 공표 시점 법인 이력6개(중국 AD3·베트남 CVD3), 기존 한국 AD5 사건 보존. 현재 적용 세율 전수검증으로 주장하지 않음.
2. 일본 열연/한국 OCTG 원문 해석 보류2건을 재확인, 유지. 정정 미발견은 정정 부존재가 아님. 채택 IDM/CBP 지침 해석 미확보.
3. 공식 13사건 실제 수집: 2026-01-01~10/15, 사건 연결57건/고유 FR문서43개, 74요청, 13/13 완료. 동일 기준일 resume은 0요청. raw HTML/SHA256/state는 비공개 로컬 `policy-downloads/remedy-review-20261015`. 공개 산출물은 검토 대기열만 커밋.
4. DataWeb2025 HS6 상위8개국 금액/표시국 소계 비중. 국내 공급/세계총액 null, 50/25/25 가상값 보존. 국가/기업 화면 JSON 연결은 사용자 검토·독립 검증 미완료. 제품·기간·평가·법인·원산지 기준을 검사하고 자료/물량 단위를 결과JSON에 보존. 실제 국내 공급/비공개 제품 원가 미확보.
5. Node127·소유권10 통과, preview 모듈 경로 및 공백검사 통과. actual mount 이벤트/정밀도/0 vs null/확인 해제 검사. 실제 브라우저/라이브 UI 미검증. 과거 브라우저 거부를 다른 surface로 우회하지 않음.

## 별도 예약

- App heartbeat ID `ad-cvd`, 이름 `AD·CVD 공식 공고 변경 점검`, 생성 결과 `ACTIVE`, 4시간 간격.
- 첫 예약 실행 자체는 아직 관찰하지 않음. 현재 성공한 것은 수동 수집 실행과 예약 생성이다.
- Mac의 로컬 파일을 쓰므로 Mac과 앱이 실행 가능한 상태여야 한다. 원격 서버/Actions 무인 운영으로 주장하지 않는다.
- 예약은 코드 디렉터리에서 실행하되 미래 snapshot은 **비공개 state-dir 안** `remedy-discovery-snapshot.mjs`로만 저장. 저장소 변경/커밋/PR/병합/배포/DB/메일/유료 AI API 없음.
- 기존 `db`, `automation`, `automation-2`, `automation-3`은 PAUSED 유지. 재개하지 않음.
- 중복 알림 기준 `last-report.json` 초기화: `cases[case_id].notices[document_id]`의 content_hash/metadata_hash/review_status, case status/error, schedule_reviews. 마지막 성공 through10/15를 기준으로 동일 pending을 매번 다시 보고하지 않는다. 내용이 변한 경우만 보고하고 기준 갱신.
- `STOP` 또는 최신 사용자 중지 지시 우선. `running.lock` 임의 삭제 금지. `blocked_until`·403/429·Retry-After 준수, 차단 우회 금지.
- API `fetch failed`였던 기본 sandbox 실행과 일반 네트워크에서 완료된 실행을 구분. 예약의 무인 네트워크 권한은 첫 실행에서 재확인해야 하며 실패하면 그 제한을 보고한다.

## 남음

- 모든 법인의 오늘 적용 예치율, 모든 후속 정정/법원/CBP 명령의 전수검증.
- 열연/OCTG의 명시적 공식 해석. 확정 전 자동 계산 보류.
- Commerce 동적 일정 페이지 자동 파싱, 법원 docket 및 CBP 지침 자동수집.
- 같은 품목/기간/평가의 미국 국내 판매, 기업 제품별 거래/원가 실제자료. 현재 임의 생성 없음.
- 선행 PR 병합 후 base main 재조정/전체 검증, 실제 렌더링, 사용자 승인 후 병합/배포.
