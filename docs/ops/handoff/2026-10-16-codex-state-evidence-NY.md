# NY21 Siena 원문 누락 보강 — 2026-10-16

Codex. 사용자 “최근14일 하원2곳밖에 없나” 점검·진행 지시에 따른 NY21 발표 한 건 보강. 전체 NY 자료조사 완료가 아니다.

- checkout: /Users/yeoninair/Documents/해운 데이터/us-ny21-primary-review-20261016
- branch: codex/ny21-primary-review-20261016
- base: packet 없는 공용 #598 (`025fb042`). 미병합 다른 주 PR 위에 쌓지 않는다. #598 main 반영 후 main retarget·재검증.

## 실제 수집과 출처

10/16 공개 API 전체1499행을 실제 확보한 원자료에서 NY33행만 분리했다. 원래 요청 완료일을 capture.fetched_at/receipt.captured_at에 유지한다. 이전 NY 영수증은 prior_capture_receipts에 보존한다. 이번 새 FEC·NY 주지사 독립지출 수집은 없다.

API `us-202sie2af2e738`는 의뢰 매체 WPTZ 기사 주소를 제공해 `unregistered_primary_host`로 보류됐다. Siena 공식10/9 발표 페이지·보도자료2p·교차표8p를 실제 다운로드하고 SHA256을 검토했다. Q4는9/30~10/6 NY21 LV496, DEM Gendebien46 / GOP Constantino42 / IND Schmidt5 / 미정8이다. 반올림 합계101을 재정규화하지 않는다. 고지된 전체 MOE4.6은 같은 LV496이며 별도 신뢰수준은 확인되지 않았다. 기관의 정확도 등급이나 당선확률로 바꾸지 않는다.

NY21 거주자의 Q5 주지사55/40을 NY 주 전체 조사로 편입하지 않았고 Q6 의회 정당 선호도도 지역구 후보 조사로 변환하지 않았다. 정확한 API 레코드 지문·공표문·표본·후보별 원문 수치에 묶인 개별 검토이며 WPTZ 모든 미래 기사를 승인하지 않는다.

## 후보 구도와 기명 후보

Clinton County 공식 NY21 샘플 투표용지 p1은 Gendebien·Constantino2명을 인쇄하고 Constantino의 fusion ballot lines를 같은 후보로 보여준다. Schmidt 캠프는 자체 사이트에서 Christopher/Chris를 같은 인물로 사용하고 write-in 출마를 명시했다. 기명 출마 주장은 캠프 원문이며 선관위 인증으로 격상하지 않는다.

ballot review는 county sample 근거의 인쇄 후보2명과 캠프가 밝힌 기명 후보를 구분한다. Q4에서 이름으로 제시한 Christopher Schmidt는 IND로 보존하며 Chris alias의 신원 근거를 남긴다. live 정책은 인쇄 주요 후보2명을 필수 대진으로 유지해 앞으로 검토된 Siena 원문 경로의 양자 조사도 자동 연결 가능하게 한다. 기명 후보를 이름으로 제시한 조사라는 한계를 quality disclosure와 카드용 limitations에 보존한다.

## 기간·자동화 경계

10/16 기준7일에는 제외,14일에는1파동. 수치상 DEM46/GOP42지만 보고된 오차 범위 안이다. 최신 조사 결과는 확정 의석 전망이 아니다. 최신 API-only 백엔드 재생성에서 하원 집계 지역구가 CA48·MN01의2곳에서 NY21을 더한3곳으로 늘어났다. UI에는 MN01의 검토된 Jake/Jacob 별칭을 문자열로 비교해 제외하는 별도 오류가 확인됐다. 이 UI 수정은 codex/poll-summary-aliases-20261016 별도 PR #599 범위이며 NY 주별 PR에 넣지 않는다. NC01·NE02·KY06은 여전히 원문/방법/의뢰·문항 검토 대기이며 미확보를0이나 승패로 채우지 않는다.

기존 일일 workflow의 주별 overlay→API 수집→정확한 레코드 검증→live/history/화면 경로를 사용한다. 원래 Siena 원문 도메인의 미래 새 조사+검토된 후보 대진은 기존 코드로 연결된다. 미래 WPTZ 기사 주소·다른 기관/의뢰자·변경된 레코드는 자동 승인하지 않는다. 원문 검토일을 자동 수집일로 매번 바꾸지 않는다.

## 검증·미완료

NY 전용6개 통과: 원문 n/수치, 인쇄/기명 분리,7/14 창, 동일 파동 중복, 표본·의뢰자·URL 변경 거절, 미래 검토 출처 연결, 타주 race/history·원래 날짜·104석 focus 보존. 전체 polling531개·finance68개·기존 선거JS90개·ops/소유권16개 및 배포연결40workflow가 통과했다. 공용 기반 polling525·finance68·JS90·ops16·deploy-chain40 검증 근거는 #598에 있다.

주별 diff는 NY packet·NY21 원문 감사·NY 테스트·이 인수 문서뿐이다. 공용 목록·전국 생성물·UI·workflow 편집 없음. 병합·배포·운영 workflow 실행·재설정 안 함. 다른 주의 다음 순서는 시작하지 않는다. #598이 게시 오류를 복구한 뒤 실제 예약 실행·서비스 기준일 갱신을 별도로 확인해야 한다.

최종 원문 감사·테스트 이름은 주별 범위 규칙의 NY- / test_poll_ny_ 토큰을 따른다. NY만 재생성 및 전체 projection 성공, 오류 없음. PR #600. 원문 한 건의 보강이며 NY 전수 완료가 아니다.
