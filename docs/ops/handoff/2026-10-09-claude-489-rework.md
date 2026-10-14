# 인수인계 2026-10-09 — claude → codex

## 2026-10-09 — claude (선거 스택 #490–#506 main 배포 + #489 재작성 요청)

### Goal / summary
선거 스택(#490→#492→#498→…→#506)을 main에 반영·배포했다. **#489(일일 폴링 +
하원 경합 104석)는 스택과 같은 폴링 파일 8개가 충돌해서 배포하지 않았다.**
이 문서는 Codex가 #489를 새 main 위로 다시 맞춰 오기 위한 요청서다.

### 현재 상태 (확인 완료)

- main = `3b2e2a0d` (`Merge stack #490-#506 ...`). 스택 20커밋이 병합 커밋으로 들어갔다.
- 배포: `Deploy to Cloudflare Workers` run 715 (main `3b2e2a0`) gate / Deploy Worker /
  LETF 검증 / 가스 검증 / 매크로 캐시 삭제 전부 성공.
  https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/37885741588
- 스모크(`/api/ticker?limit=3`)는 이 세션의 외부 접속 제한으로 **실행하지 못했다.**
  사람이 확인할 것.
- 이번 병합으로 바뀐 것은 데이터뿐이다 (`elections_board_v1.json`,
  `usa_election_live_polls_v1.json` 등). UI·워크플로·`_worker.js` 변경 없음.
- 반영한 PR: #506 하나를 base `main`으로 바꿔 병합했다. #490–#505는 base가
  main이 아니었으므로 GitHub에서 아직 open일 수 있다 (커밋은 모두 main에 있음).
- 넣지 않은 PR: **#489**(이 문서의 대상), **#496**(commodity_trade_refresh 워크플로
  파싱 수정 — 선거와 무관, 사용자가 제외).

### #489 재작성 요청

기준: **새 main `3b2e2a0d` 위로 `codex/us-house-poll-priority-20261008`을 다시 맞춘다.**
원본 PR 브랜치(`3c26951`)와 스택 브랜치는 건드리지 않고 새 브랜치에서 작업하는 것을 권장.

충돌 8개 (사전 검토 문서의 3-way 재현과 동일):

- `New for anti/public/data/usa_election_live_polls_v1.json`
- `New for anti/public/data/usa_election_poll_history_2026.json`
- `New for anti/scripts/election_watch/config/usa_polls/ballot_reviews_2026.json`
- `New for anti/scripts/election_watch/config/usa_polls/quality_reviews_2026.json`
- `New for anti/scripts/election_watch/config/usa_polls/live_2026.json`
- `New for anti/scripts/election_watch/election_watch/live_polls.py`
- `New for anti/scripts/election_watch/refresh_live_polls.py`
- `docs/ops/TASKS.md`

hunk 수(live_polls_v1.json 174 등)는 비교 방식에 따라 달라지므로 기준으로 쓰지 말 것.

### 지켜야 할 조건 (Codex 사전 검토 문서에서 확인된 것)

1. **생성 JSON은 손으로 합치지 않는다.** 코드·설정을 통합한 뒤 수집기로 다시 만든다.
   live/history뿐 아니라 status·forecast 생성물도 포함.
2. **전국 수집기의 보존 문제를 먼저 고친다.** 스택의 `refresh_live_polls.py`를 그대로
   돌리면 `state_captures` 50개 → 0, 레이스별 기존 `fetched_at` 506개 → 0,
   history 55개 → 0이 된다 (오프라인 재생으로 재현됨). 새 조회 시각과 과거 원문·주별
   수집 시각을 분리해 보존할 것. 과거 `fetched_at`을 새 조회 시각으로 바꾸거나, 새
   API 조회를 과거 영수증의 수집 성공으로 해석하지 말 것.
3. **#489의 원문 근거 정정과 스택의 지문 검증을 함께 보존.** 정정 순서가 바뀌는 경우를
   테스트한다. coverage는 원본 API 응답 기준이며, 원문 보완 응답을 API 레코드 수로
   세지 않는다.
4. **`ballot_reviews_2026.json`은 후보 신원 단위로 비교.** 최신 공식 본선 명부와 검토된
   별칭을 보존하고, 예전 경선·탈락 후보를 되살리지 않는다. 파일 전체를 한쪽으로
   고르지 말 것 (#489 변경 11개 레이스 중 10개가 스택과 겹침).
5. **품질 검토가 양쪽에서 바뀐 3건은 스택의 후속 원문 검토를 우선 대조:**
   FL-22 `us-202tav1ccea6ab`, VA-01 `us-202the7176ba8a`, VA-05 `us-202thec3b2cee5`.
   FL-22의 미확인 LV·정보제공 후 강제 선택 문항을 대표 조사로 승격하지 말 것.
   VA-05의 원문 대조 수치 정정(Perriello 46→45)을 되돌리지 말 것.
6. **`house_poll_focus` 재계산 연결.** `state_poll_capture.merge_capture()`가 기존 board를
   복사한 뒤 주별 값을 갱신하지만 focus 집계를 다시 계산하지 않는다. 주별 갱신 후
   focus의 레이스별 개수·7/14일·검토 대기·finance join이 실제 board와 일치하는
   검사를 추가한다 (코드상 확인한 누락 경로이며 실행으로 검증된 수정은 아님).
7. **104석은 고정 수가 아니다.** Cook 경합 43 + 사용자 추가 61을 구분하고 현행 입력에서
   매번 재계산한다 (기존 설계 유지).
8. **워크플로:** `deploy.yml`은 건드리지 않는다. polling workflow의 `name:`은
   `US election polls weekly` 그대로 둔다 — deploy의 `workflow_run`이 이 이름을 참조한다.
   소유권 예외는 #489 브랜치의 `.github/workflows/us_election_polls_refresh.yml`
   한 파일로만 유지. `tools/ops/check_deploy_chain.py`로 이름 일치 재확인.
9. 결측을 0이나 승패로 메우지 않는다. 7/14일·선거 종료·원문 장애 시 마지막 유효 자료와
   원래 기준일 보존을 검사한다.

### 완료 기준 (Claude가 배포 전에 확인할 항목)

- 새 main 대비 `mergeable_state: clean` (충돌 없음).
- polling / finance / JS 선거 계약 / 소유권 범위 / `check_deploy_chain.py` 통과 결과가
  PR 본문에 있다.
- 재생성 전후 비교에서 `state_captures`·`fetched_at` 계보가 보존됨을 보여 준다.
- 기존 사용자 배포 보류가 걸려 있으면 PR 본문에 해제 여부를 적는다.
- 위가 충족돼 PR이 올라오면 알려 달라. Claude가 CI·mergeable 확인 → ready 전환 →
  merge → 배포(`deploy.yml`) → 스모크 순서로 진행한다.

### 알아 둘 것

- main은 시간당 티커 등 봇 커밋으로 계속 움직인다. 작업 시작 시 main SHA를 다시 고정할 것.
- 스택의 주별 수집 일정(IA/TX/WI/AZ/NV 예약 등)은 Actions에 설치된 것이 아니다. 이번
  병합으로 새 workflow는 추가되지 않았다.
- 사전 검토 문서(`integration-review.ko.md`)는 Codex 로컬 산출물이라 Claude는 업로드본으로만
  읽었다. 이 레포에는 없다 — 필요하면 `docs/ops/handoff/`에 포함시킬 것.

### Remaining TODO

- [ ] Codex: #489 새 main 기준 재작성 + 위 검증
- [ ] Claude: 재작성 PR 확인·병합·배포·스모크
- [ ] 사람: 라이브 `/api/ticker?limit=3` 스모크, 선거 화면 확인
- [ ] 정리: #490–#505 open PR 닫기 여부 결정 (커밋은 이미 main에 있음)
- [ ] #496 별도 처리 여부 결정
