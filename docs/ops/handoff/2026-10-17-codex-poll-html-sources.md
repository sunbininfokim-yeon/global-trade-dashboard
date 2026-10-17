# API 없는 HTML 여론조사 원문 편입 기반

- 담당: Codex. checkout `us-poll-html-sources-20261016`, branch `codex/poll-html-sources-20261016`.
- 사용자 요청: 취합 사이트 표에서 발견한 조사도 API 유무와 무관하게 원문 검토 후 반영.
- 기반 PR만 포함: 주별 packet, 전국 생성 JSON, UI, workflow 변경 없음. 병합/배포 미실행.

## 구현과 연결

`inspect_poll_html.py`는 저장한 원문 HTML과 검토한 URL/영역(tag+id)/시작·끝 문구를 읽어 검토용 텍스트와 SHA256을 생성한다. 표 셀 간 공백을 보존하고 script/style/template/noscript는 제외한다. 출력은 검토 입력이며 그 자체로 조사·승패를 만들지 않는다.

`poll_primary_supplements.merge_primary_supplements`에 `reviewed_html_region_v1`을 연결했다. 기존 주별 packet의 정확한 발표·문서 검토를 통해서만 승인되며, 같은 도메인의 모든 미래 발표를 승인하지 않는다. 기존 일일 수집/주별 수집이 이 함수를 호출하므로 별도 API나 workflow 변경 없이 검토된 HTML 발표를 재확인할 수 있다.

주별 편입 순서: 원문 확보 → HTML 영역 추출 → 후보/문항/기간/LV·RV/문항 표본/의뢰자/방법론·수치 검토 → 해당 주 quality review와 primary supplement operation → 실제 주별 수집 및 packet 동결 → 임시 전국 산출물 재생성. 기존 `refresh_state_polls.py --state <STATE> --packet`과 `freeze_state_inputs.py`를 사용한다. 본 PR은 이 절차의 공통 HTML 형식을 추가한다.

## 보존과 중복

광고/메뉴/관련 기사 변경은 영역 밖이면 지문에 영향을 주지 않는다. 영역 내부 수치·방법론 변경, 영역 중복/소실, 접근 실패는 종전 수치와 원래 조사일을 참고 전용으로 이월한다. 같은 API 파동은 기존 표본/수치/의뢰자/내부조사 일치 검사를 통과해야 중복 제거되며 충돌하면 게시를 보류한다. 7/14일, 후보 신원, 경선/본선, 품질 계약은 기존 정규화가 계속 판정한다.

## 실제 원문 확인

- Emerson/Nexstar CT 10/15 발표: 실제 HTTP HTML의 `main#main`에서 본문부터 의뢰자 문장까지 추출 성공. LV800, 조사10/10–12. 원문 표의 소수점 결과와 보도자료 반올림값은 서로 구분해야 한다. 이 기반 PR은 CT 조사 데이터를 게시하지 않는다.
- CNU/Wason VA02 10/14 발표: 실제 HTTP HTML의 `main#main-content`에서 조사 분석과 방법론까지 추출 성공. LV702, 조사10/1–10. VA02 응답자의 상원 문항은 버지니아 전주 조사로 바꾸지 않는다. 본 PR에서 VA packet 변경 없음.
- RealClearPolling 직접 HTTP 요청은403. 검색/브라우저에서 보인 표를 무인 수집 성공으로 표현하지 않는다. NYT·Race to the WH 등 전체 사이트의 미래 발표 자동 수집은 이번 공통 형식만으로 보장되지 않는다.

## 검증

추출/변경/장애/중복 테스트8개 및 기존 PA 원문·270toWin 발견 테스트 포함26개 통과. 실제 HTML2개에서 추출 성공. 전체 polling/기타 검사 결과는 PR에 기록한다.

추가 통합 검증: HTML 원문 재확인 → 기존 normalize → 7일 미포함/14일 포함 → 원문 변경 시 집계 제외 통과. 운영 데이터가 아닌 기존 PA 테스트 레코드와 합성 HTML을 사용하는 회귀 검사이며 새 실측 조사로 세지 않는다. ops16·배포 연결40 통과.

GitHub 최초 검증551개 중550개 통과. OR 금융 연결 테스트1개가 새 게시 자료를 과거 고정일10/14와 비교하여 `future polling snapshot`으로 실패했다. 공통 기반 PR에서 해당 테스트의 게시자료 조인 기준일만 기존 `PUBLIC_SNAPSHOT_DAY`로 전환했다. 원래 OR 조사일·수집일·입력·금액은 변경하지 않는다. JS92·finance68 통과.
