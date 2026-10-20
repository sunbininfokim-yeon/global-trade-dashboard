# 공개 발표 발견 확대·Cursor 조사 편입 대기열 — 2026-10-21

사용자: Toss-Up·Lean 우선 자동 수집 출처 확대와 발견→검토→편입 대기열 진행. 병합·배포는 보류한다. 공용 기반 작업이며 특정 주 packet을 추가하지 않는다.

- checkout: `/Users/yeoninair/Documents/해운 데이터/us-ne-research-integration-20261020` (이전 작업을 전부 push한 뒤 순차 재사용)
- branch: `codex/poll-discovery-intake-20261021`
- base: main `5a08711d5f196f6bae98a7b58b8d55f5257d5b37`
- #651 복구 및 #644/#649 수집 확장과 독립 검토. 일일 전국 수집 복구에는 #651이 먼저 필요하지만 이 PR에 그 diff를 복사하지 않는다.
- UI·workflow·전국 생성 JSON·주별 입력·소유권 예외·main 병합·배포·운영 workflow dispatch 변경 없음.

## 실행 경로

기존 일일 Actions는 `discover_poll_sources.py --output "$RUNNER_TEMP/us-polls-capture.discovery.json" --provider-capture "$RUNNER_TEMP/us-polls-capture.provider.json"`을 이미 실행하고 `us-polls-capture*.json`을 artifact로 보관한다. 이를 그대로 사용한다.

1. 270toWin·RTWH에 더해 Emerson 공식 RSS, Quinnipiac 공식 결과 목록, Suffolk 공식 최신 발표를 조회한다. 날짜는 **기사 게시일**로 저장하며 조사기간으로 바꾸지 않는다. 문항 수치·표본·경선/본선·statewide/bellwether를 자동 승인하지 않는다. 최초 방문 URL과 최종 URL이 다르면 오류 페이지를 정상 수집으로 기록하지 않는다.
2. `scripts/election_watch/research/2026/<STATE>/*_records.json`이 Git에 들어오면 기존 일일 발견 실행에서 자동으로 읽는다. 저장소 밖 자료는 `--research-dossier`로 명시해 비게시 검토할 수 있다.
3. 발견 결과에 Cursor 원문 해시·문항별 메타데이터 검사 결과를 함께 저장한다. provider 원자료의 SHA-256을 발견 artifact에 연결한다.
4. 기존 `--retry-capture` 게시 경로가 같은 이름의 `.discovery.json`을 읽어 원자료 시각·지문·cycle/as_of를 대조한다. 전체 대기열은 별도 `usa_election_live_polls_intake_v1.json`, 지도용 `board.poll_intake`에는 요약과 파일 경로만 저장한다. 이전 pending 문서와 원래 발견일을 보존하고 내용 변경은 별도 version으로 남긴다. artifact 장애/불일치·쓰기 실패 시 종전 대기열을 보존하며 건강한 여론조사 수집은 계속한다. 새 파일은 기존 artifact glob에 포함되며 기존 publisher는 정확히 그 파일이 존재할 때만 추가로 stage한다. raw 연구 파일을 게시하지 않는다.
5. 우선순위는 현행 `house_poll_focus`로 재계산한다. 과거 요청 수 104를 하드코딩하지 않는다. 기존 주별 영수증·관측·7/14일 우세 집계·정당 수치를 바꾸지 않는다.

`primary_review_required`, `research_gaps`, `ready_for_human_review`, `race_identity_unresolved`은 모두 **대기열 상태**이다. `ready_for_human_review`도 국가 집계 승인이 아니다. source URL 일치도 같은 조사 파동이라는 증거로 사용하지 않는다. 본문 전체를 공용 JSON에 복제하지 않고 발표 제목·게시일·참조 URL·문맥 지문을 남긴다.

## Cursor에게 전달할 조사 계약

한 주·한 worktree·한 독립 PR을 유지한다. 파일은 `research/2026/<STATE>/<STATE>_2026_records.json`과 옆 `raw/`에 둔다. 전국 JSON·공용 목록·다른 주 packet은 수정하지 않는다. 기존 `usa_state_research_dossier_v1`은 계속 읽지만 부족한 필드는 보류 사유로 표시된다.

조사마다 원문 URL·실제 내려받은 파일·SHA-256·기관·의뢰자 또는 원문의 독립 조사 선언·기간·모집단·방식·가중치를 수집한다. checked_on은 실제 검토한 UTC 날짜를 쓴다. **문항마다** 선거 종류·지역구·정확한 질문·최초 투표 문항 여부·표본 n과 표본의 기준·지리 범위·후보별 수치를 따로 적는다. statewide n을 House 문항 n으로, unweighted n을 가중 표본으로, undecided나 누락 값을 0으로 바꾸지 않는다. 원문에 없으면 null과 missing_fields를 남긴다.

아래는 빈 양식이며 실제 값과 원문 없이 실행·승인할 자료가 아니다.

```json
{
  "schema": "usa_state_research_dossier_v1", "cycle": 2026,
  "state": "<STATE>", "checked_on": "<실제 검토일>",
  "polls": [{
    "id": "<기관-주-실제 조사기간>", "source_url": "<원문 https URL>",
    "local_file": "raw/<파일명>", "sha256": "<실제 파일 SHA-256>",
    "pollster": null, "sponsor": null, "sponsor_statement": null,
    "field_start": null, "field_end": null, "released_on": null,
    "population": null, "sample_n": null, "mode": null, "weighting": null,
    "questions": [{
      "office": "house", "district": null, "stage": null,
      "geography_state": "<STATE>", "geography_scope": "district",
      "initial_ballot": null, "prompt": null, "ballot": null,
      "sample_n": null, "sample_base": null, "population": null,
      "results_pct": [{"label": "<원문 표기>", "candidate_name": null, "party": null, "pct": null}],
      "location": null
    }],
    "missing_fields": []
  }]
}
```

상원/주지사는 district=null, geography_scope=statewide를 사용한다. `candidate_name`은 기존 검토 명부의 정확한 이름을 별도 확인해 적고 원문 label은 보존한다. 철자·별명·정당을 추측으로 고치지 않는다. 원문 밖 동영상·기사 요약·당선확률·예측 평균은 원문 조사 수치로 입력하지 않는다. 질문 전체가 없는 숫자 조각은 `reported_figures_not_complete_ballots`에 보존한다. 새 기관의 미래 발표 전체를 승인하는 요청은 넣지 않는다.

## 비게시 실행

```sh
python3 build_poll_intake.py --research-dossier /path/to/STATE_2026_records.json --output /tmp/poll-intake.json
python3 build_poll_intake.py --discovery /tmp/us-polls-capture.discovery.json --previous /tmp/previous-intake.json --output /tmp/next-intake.json --tasks-output /tmp/research-tasks.json
```

검토자가 정확한 원문·후보·문항·의뢰자·표본을 확인한 뒤 기존 주별 `config/state_evidence/2026/<STATE>.json` 검토 작업으로 넘긴다. 이 PR은 대기열을 원문 승인 목록으로 자동 변환하지 않으며 숫자를 복사한 것만으로 집계하지 않는다.

## 검증과 실제 실행 결과

실제 공개 API를 한 번 새로 조회해1540개 원자료를 받았다(as_of2026-10-20 UTC, captured_at2026-10-20T21:46:02.289524+00:00). 이전1511과의29개 차이를 새 조사29건으로 해석하지 않는다. 새 대학 목록에서는11개 주·18개 선거에 연결되는 발표 후보22건을 발견했다. 기존 취합 목록까지 포함한 전체 발견은1385행이며, URL/선거별 문서 검토 작업은1097개(경선·과거·미해결 지역 포함)다. 집계 적격으로 자동 승인한 건수는0이다.

기존104개 하원 우선 선거 중52곳에121개 문서 검토 후보가 있다. 나머지52곳은 이 발견 결과에서 후보 문서를 얻지 못한 것이며 실제 조사가 없다는 뜻이 아니다. 우선순위 작업 JSON `/private/tmp/poll-intake-20261021/research-tasks.json`은 검토한 명부의 현재 이름·정당도 함께 제공하지만 이를 원문 후보 표기의 자동 정정 근거로 삼지 않는다.

사용자 제공 NE Cursor dossier를 파일 복사/수정 없이 읽어9개 문항 후보를 검증했다. 원문 파일 지문은 모두 일치했으며7개 문서/선거 검토 작업에 묶였다. 누락된 문항별 표본·범위·게시일·후보 신원 등은 보류하며0이나 완전한 조사로 채우지 않았다. dossier의 기존 checked_on·조사기간·수치는 보존하고 대기열에 실제로 들어온 수집 시각을 별도로 기록한다. 날짜만 있는 검토일을00시 수집시각으로 만들지 않는다.

main 기반 최초 전체844개, 후속846개 검사는 통과했다. 별도 파일 게시·오프라인 CLI 검사를 추가한 최종 전체 검사를 실행 중이다. JS114개, 소유권14개, 배포연결42 workflow 검사를 통과했다. 최종 결과·PR 번호는 완료 시 기록한다. 실제 수집/검토 출력은 모두 `/private/tmp/poll-intake-20261021`에만 저장했다. 전국 배포 파일에는 쓰지 않았다.

#651 및 #649 각각과 `git merge-tree --write-tree` 충돌 없음. #651 합본은 브랜치 병합 없이 임시 코드로 내보내1540개 API 입력을 보존한 채 실제 원문 문서 재확인을 수행했다(보완 후1574행·영수증40개). 동일 provider captured_at를 유지한 비게시 재생에서219개 관측·136개 집계 적격 과거 포함 관측을 얻었다. 새 대기열 문서의 자동 집계 승인0건과 구분한다. #651 복구가 일일 수집에 먼저 필요하며 이 PR은 독립 main 기반이다. API·원문·대기열을 재생한 것이 main 또는 사이트 반영을 뜻하지 않는다.
