# 인디애나(IN) — 주별 입력·후보 원문 감사

담당 주 IN(C그룹), checkout `/Users/yeoninair/Documents/해운 데이터/us-in-evidence-input-20261016`, branch `codex/in-evidence-20261016`. 최신 main `77f52560a0bab98e9ad670f8238018d5df50f18f`에서 독립 분기. MT 등 미병합 주별 PR을 기반으로 쓰지 않는다. 다음 IL은 시작하지 않는다.

실제 공개 API 수집: 2026-10-16T04:13:47.960144+00:00. IN 원자료 0건, 원래 receipt/응답 지문을 보존했다. 추가 전체 API 응답의 Indiana 및 IN 지역구 subject를 넓게 검색해도 0건이었다. API 0건은 실제 조사 부재의 증거가 아니다. 정상 main 일일 수집은 기존 9개 하원 discovery slot을 읽으며, 등록된 기관/출처·현행 후보와 일치하는 새 조사를 연결한다. 모든 기관·원문을 포괄 승인하지 않는다.

공식 주 선거관리부 XLSX(Candidate_List_Abbreviated_20260922_011251PM.xlsx)를 실제 내려받아 하원 9곳, 일반 후보 21명·기명투표 등록 5명을 분리해 audit에 보존했다. 파일 버전 9/22와 10/16 검토일은 구분한다. 기존 법적 이름/후보 ID를 새로 인증된 전체 명부로 승격하지 않는다. Johnson 기명투표 명칭이 기존 명부와 달라 자동 신원 이전하지 않는다. 상원·주지사는 2026년 선거 대상이 아니며 주의회/주무장관 조사는 편입하지 않는다.

IN-05 Impact Research/Ford 캠프 조사 발표를 공개 집계 목록에서 발견했고 reporter 원문 링크 `https://x.com/DanSpehler/status/2085077555984396724`까지 추적했다. 원문 접근·질문·표본·방법론이 검증되지 않아 audit의 discovered_held_releases에 보류한다. 집계 사이트의 수치·표본을 정상화 관측으로 만들거나 최근 7/14일 승패로 쓰지 않는다. 원문 검증·적격 판정 후 정확한 발표만 편입해야 한다. API 미수록/발견 후 보류/원문 검증 완료를 구분한다. source audit 경로는 receipt의 source_discovery_review_data_file로 연결한다.

기존 FEC 자료: 후보 ID 19개, 현재 후보 지출 관측 2개 지역구. 원래 federal_last_success_at=2026-10-12T18:25:08.136419+00:00, finance index=2026-10-12T18:25:22.502460+00:00. 새 FEC 금액 수집이 아니며 후보 캠프 수입을 독립지출로 만들지 않는다. Rudy Yakym와 J.D. Ford 및 기명투표 등록 5명의 미검증 ID는 null을 유지한다. 지출 미관측 7개 지역구를 0달러나 미지원 수집기로 단정하지 않는다.

IN 전용 회귀 4개 통과: 공식 원문 일반/기명 후보 구분, 9곳 전체의 새 등록 출처 API 조사 편입과 잘못된 구 후보 거절, 발견 자료 미편입, 단독 replay의 타주 레이스·이력·전역 날짜·원래 receipt 보존. 테스트 가상 수치는 테스트 파일에만 있으며 실제 데이터가 아니다. 전체 polling/JS/범위 및 GitHub 결과는 PR에 별도 기록한다.

전국 산출물은 임시 사본에서만 재생성한다. 주별 PR은 packet/원문 감사/IN 테스트/이 문서만 포함하며 공용 검토 목록·수집기·UI·workflow·LETF·TASKS는 수정하지 않는다. 원본 source dates와 null을 유지한다. 공개 수집에 새 API 키는 필요하지 않았다. 병합·배포·운영 workflow 실행은 하지 않는다.
