# 2026-11-24 Claude: 선거 정적 파일 고아 해시 정리

브랜치 `claude/election-asset-prune`. base는 `f6c09752`(main)다.
선행 문서는 `2026-11-24-claude-asset-orphan-prune.md`(#1092)다. 무역 정리는 이 PR에 넣지 않았다.

## 한 줄

선거 해시 파일 9,461개를 지워 배포 대상 정적 파일이 20,759개에서 11,298개가 됐다(`.assetsignore` 반영). 이 PR만으로도 20,000개 한도 아래다.
생성기는 이제 인덱스를 발행한 뒤 도달할 수 없는 옛 해시 파일을 지운다. PR 검사로 재발을 막는다.

## 선행 문서와 다른 점 (중요)

- **인덱스 하나만 기준으로 하면 쓰는 파일까지 지운다.**
  - `usa_election_live_polls_v1.json`은 선거자금 race 파일 470개를 직접 가리킨다. 이 파일들은 금융 인덱스로는 도달하지 않는다.
  - `usa_election_poll_release_reviews/2026/CO-primary-20261009.json`은 주별 근거 파일 1개를 직접 가리킨다.
  - 그래서 도달성 판정의 출발점을 "자산 폴더 밖의 모든 `public/data` JSON"으로 넓혔다.
- 고정 이름 파일 3개는 고아처럼 보이지만 스크립트가 직접 읽는 입력이라 삭제 대상에서 뺐다.
  - `governor_context_inputs_v1.json`, `governor_context_status_v1.json`, `candidate_fundraising_status_v1.json`
  - 삭제 대상은 `-<16hex>.json` 파일만이다.
- `refresh_house_candidate_rosters.py`는 `races/*-house-*.json`을 glob으로 전부 읽는다.
  - 옛 파일에만 있는 후보 튜플이 52개 있다.
  - 전부 읽을 때와 살아 있는 파일만 읽을 때의 `attach_verified_finance_ids` 결과를 시뮬레이션했고, 차이는 0이다.
- JS는 인덱스의 `data_file`로만 읽는다. 파일명을 조립하는 코드는 없다.

## 바뀐 것

- `election_watch/asset_prune.py`: `reachable` / `stale` / `prune` / `unretained`
  - 현재 루트나 직전 세대 인덱스가 도달하는 파일은 보존한다.
  - 파싱할 수 없는 루트가 있으면 중단한다.
- 생성기 연결:
  - `build_superpac.publish`: `usa_superpac`
  - `build_superpac_map.build`: `usa_election_finance`
  - `state_evidence.publish_states`: `usa_election_state_evidence`
  - 모두 인덱스를 원자적으로 교체한 뒤 실행한다. 직전 인덱스 한 세대를 보존한다.
  - 주별 근거는 그 실행에서 처리한 주만 정리한다.
- `publish_polling_run.stage_paths`: 근거 폴더의 삭제분(`git ls-files --deleted`)만 추가로 stage한다. superpac 워크플로는 이미 `git add --all`을 쓴다.
- `prune_election_assets.py`: 1회 또는 수동 정리용이다. 기본은 dry-run이고, `--apply`를 줘야 지운다.
- `tools/ops/check_static_assets.py` + `.github/workflows/static_assets_guard.yml`(PR 검사)
  - 배포 대상이 18,000개를 넘으면 경고, 20,000개를 넘으면 실패한다.
  - 같은 shard에서 도달 불가 세대가 2개 이상이면 실패한다.
- `tests/test_election_asset_prune.py`

## 1회 정리 결과

직전 세대 루트는 각 파일을 바꾼 바로 전 커밋에서 가져왔다.

| 파일 | 커밋 |
|---|---|
| finance / superpac index | `ecfd3111` |
| state evidence index, live polls | `5ec54246` |

| 폴더 | 전 | 삭제 | 남음 |
|---|---|---|---|
| usa_election_finance | 9,532 | 7,663 | 1,869 |
| usa_superpac | 653 | 559 | 94 |
| usa_election_state_evidence | 1,324 | 1,239 | 85 |

## 검증

- `public/data` 전체에서 선거 폴더 참조 3,380개를 검사했다. 존재하지 않는 파일은 0개다.
- `check_static_assets.py`: 11,298개, 보존 초과 shard 0개
- `test_superpac*` 79개, `test_election_asset_prune`, `test_poll_state_evidence`, `test_poll_state_inputs`, `test_poll_projection_review_clock`, `test_poll_intake` 등 관련 테스트가 전부 통과했다.
- `check_deploy_chain.py` 통과
- 헤드리스 화면 확인과 wrangler dry-run은 사용자 요청(토큰 절약)으로 생략했다. 참조 존재 검사로 대신했다.

## 남은 것

- 병합 후 선거 화면(주별 자금·Super PAC·후보 대결)에서 콘솔 404를 확인한다.
- 무역 `commodity_trade_bilateral_v1`: 별도 세션·PR(#1091 참고)
- #1092 `.assetsignore`는 이 PR과 독립이다. 둘 다 병합해도 충돌하지 않는다.
