# 미국 선거 본선 후보 명부와 상원 35석 UI

- 작업: `T-ELECTION-MATCHUP-20261008`, `codex/usa-election-ui`.
- 기준: 2026-10-08 KST 작업, 후보 명부 검토 날짜는 실제 수집 UTC 기준 2026-10-07.
- 현재 범위: 사용자 요청에 따른 선거 UI와 명부 연결. 병합·배포 보류를 유지한다. 기존 PR #478은 2026-10-07T16:06:04Z 병합된 상태를 확인하고 최신 main을 통합했다.

## 왜 후보가 미확정으로 보였나

최신 여론조사 판의 100개 감시 레이스 중 48곳은 `required_candidates`가 빈 감시 자리표시였다. 이는 조사 후보 대진 검토와 공시 후보 조인 준비 상태이며, 경선 진행 상태의 공식 기록이 아니다. CA-01은 감시 목록에조차 없었다. FEC 등록 후보는 경선 탈락자·과거 선거 후보도 포함하므로 그 명부를 본선 후보로 자동 승격하지 않는다.

후보 명부를 `state.election_matchups`로 독립시켰다. 지역구 선택 패널은 현직 의원 아래에 이번 선거 구도를 DEM/GOP 후보 박스로 보여준다. 공식 명부에서 한 정당 후보가 없는 경우와 명부 미연결을 구분한다. 같은 정당 두 후보, 무소속 후보도 보존한다. Louisiana의 2026 상원은 봄 당내 경선, 하원은 11월 공개 경선 방식이므로 하원에만 공개 경선 설명을 붙인다.

## 연결 범위와 근거

- 신규 표시 명부: 상원 35개 선거 전부, 하원 95개 지역구. 총 130개.
- 공식 인증: CA 하원 52개(완전한 두 결선 후보), NY 하원 10·17구(인증 PDF의 주요 정당 후보만 검토). 공식 54개, 보도·검토 명부 76개.
- 기존 Cook 하원 Lean/Toss-up 43개와 상원 Lean/Toss-up 8개 전부 후보 표시 가능. 사용자 추가 경합 분류의 모든 지역구까지 명부가 완성된 것은 아니다.
- 나머지 하원 340개는 이번 신규 명부 범위 밖이다. 빈 감시 명부 중 미연결 8개는 GA-01/03/09/11/14, TN-07/08, AL-02. 화면은 경선 미완료로 단정하지 않는다.
- 주지사 후보와 공시 금액은 최신 main의 기존 연결을 보존한다. 이번 작업은 주별 독립지출 추가 수집이 아니다.

명부 출처:

1. CA 인증 명부: https://elections.cdn.sos.ca.gov/statewide-elections/2026-general/cert-list-candidates.pdf (선거당국 공식 PDF, 52구 전수·각 2명 파싱 검증).
2. NY 인증 명부: https://elections.ny.gov/certification-november-3-2026-general-election (September 17 amended certification, 10·17구만 수기 검토. 제3당 전체 명부로 표시하지 않음).
3. 상원 35개 주요 후보: https://www.uspresidentialelectionnews.com/2026-senate-elections/ (공개 보도 명부, 공식 투표용지 전수 인증과 구분).
4. 하원 경합 주요 후보: https://www.uspresidentialelectionnews.com/2026-house-elections/ (공개 주요 후보 명부. 해당 표의 Cook 등급은 수입하지 않음. 기존 공식 Cook 검토 자료 유지).
5. NE 무소속 Dan Osborn과 SD 무소속 Brian Bengs는 검토한 공개 후보 자료에 출처를 기록. 전체 제3당/기명투표 명부의 완전성을 주장하지 않음.
6. Louisiana 제도: https://www.sos.la.gov/elections-voting/how-candidates-are-elected .

## 상원 숫자와 목록

- 현재 100석: DEM 45 / GOP 53 / 무소속 2.
- 비선거 유지 65석: DEM 32 / GOP 31 / 무소속 2.
- 이번 선거 35석의 현재 보유: DEM 13 / GOP 22.
- 선거 대상 35석만 DEM/GOP(Solid·Likely), Lean, Toss-up으로 분류한다. 전체 조건부 전망은 비선거 유지 + 35석의 전망이며 조사 부족은 미정.
- 정기 33석 + FL/OH 특별선거 2석. 상원 Class로 선거 대상 현직을 정확히 매칭하며, 비선거 NY 등은 이번 선거 후보로 보여주지 않는다.
- 35석 목록은 주/상원/등급 한 줄, 현직 정당·이름·선수를 굵게 표시하고 옆에 경쟁 후보를 둔다. 불출마 현직은 이번 본선 불출마 표시 후 아래에서 실제 본선 후보를 비교한다.
- 선수는 상원 당선 횟수. Alaska Dan Sullivan은 2선, Maine Susan Collins는 5선, John Cornyn은 4선. Moody/Husted/Armstrong/Graham은 임명. 하원 경력이나 Class를 세지 않는다.
- 선수 근거는 unitedstates/congress-legislators 공개 재임 이력의 검토 스냅샷이며 https://www.senate.gov/senators/NewSenators.htm 로 임명/초기 당선 유형을 대조. Collins/Booker는 공식 Bioguide를 추가 확인했다. 모두 공식 선거 결과 전수 이력으로 포장하지 않는다.

## 데이터 계약과 갱신

`config/federal_matchups/2026.json` → `election_watch/federal_matchups.py` 검증 → `build_board.py`의 state cards 및 `publish_federal_matchups.py` → `public/data/elections_board_v1.json` → UI.

`python3 publish_federal_matchups.py --as-of 2026-10-07`는 검토 명부만 USA states에 원자적으로 적용한다. 반복 실행 결과는 동일하며 다른 국가·기존 메타데이터는 그대로다. 검토 전/미래 날짜·중복·상원 35석 누락·선거구 범위 모순·출처 자격증명·당선 이력 중복은 실패한다. 본선 후보를 여론조사 수치 채택 승인으로 쓰지 않는다. 후보 대진이 다르면 최신 조사/조건부 전망/지도 조사 우세색을 보류한다. 본선 명부는 현재 검토 스냅샷이며 전국 선거당국 명부의 자동 다운로드까지 완성한 것은 아니다.

외부 지출은 기존 명시적 G2026만 표시한다. 후보 매칭은 정확한 후보 ID 또는 검토된 이름·정당의 유일한 매칭으로 제한한다. Mike/Michael Lawler, Troy/Troy Dale Jackson, John/John E. Sununu의 별칭은 이번에 같은 선거/정당 명부를 검토한 세 건만 명시했다. 미수집은 0으로 채우지 않고 경선·과거·UNKNOWN 금액을 본선 지출로 합치지 않는다.

## 검증

- 선거 JS 테스트 51개.
- 본선 명부/파서/마지막 정상 파일 보존/선수 검증 6개.
- 기존 여론조사 우선순위·전망·출처 채택 42개, 기존 여론조사 계약 11개, 상원 임기 오버레이 2개, 소유권 예외 5개.
- 기존 board는 이번의 election_matchups/senate_election_history 필드를 제거하면 최신 main과 값이 동일함을 확인.
- 로컬 실제 페이지: 전국 100/65/35 숫자, 35개 상원 후보 카드, Lean 칩 펼치기/재클릭 접기, Lean CA-13 클릭 후 주별 현직+DEM/GOP 후보, CA-01 직접 진입을 확인.
- 선거 모듈/스타일 캐시 버전을 올렸다. 앱/LETF/배포 workflow 변경 없음. 신규 API 키 사용 없음. 임시 정적 서버의 FRED API 오류는 기존 금융 모듈이 로컬 backend 없이 요청한 것으로 선거 모듈 오류와 분리했으며, 금융 파일은 수정하지 않음.

예약 `automation-2`는 별도의 기존 선거 데이터 공백 보강 작업이며, 이 UI 파일을 동시에 수정하지 않도록 프롬프트에 명시했다. 배포는 수행하지 않았다. PR #483 생성 후 갱신된 main의 PR #481 줄바꿈 및 원자재 화면 캐시 변경을 보존하여 index.html 충돌을 해결했다. 선거 캐시를 v14로 구분하고, PR의 기본 브랜치 대비 변경에는 원자재/인도 모델 파일이 포함되지 않는다.
