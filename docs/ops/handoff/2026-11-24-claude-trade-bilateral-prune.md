# 2026-11-24 Claude: 무역 상대국(commodity_trade_bilateral_v1) 고아 parts 정리

브랜치 `claude/trade-asset-prune`, base `3b6285ac`(main). 선거 정리 #1097과는 별도 PR이다.

## 한 줄
목록에 없는 parts 7,168개를 지웠다(8,448 → 1,280). 남은 1,280개는 현재 index 640개와 직전 index 640개다.
파이프라인은 이제 release gate를 통과한 뒤 같은 방식으로 정리한다.

## 확인한 것
- 브라우저는 parts를 `index.json`의 `entries[].path`로만 연다(`trade-monthly.js` `loadPart`, 경로 정규식 검사).
- `index.json` 전체에서 `parts/` 문자열 640개가 전부 존재한다.
- `commodity_trade_coverage_v1.json`도 같은 640개 경로를 담고 있다.
  - JS는 이 경로로 parts를 열지 않는다.
  - 같은 파이프라인의 `coverage` 단계에서 재생성되고, `validate_release`가 index와 일치하는지 강제한다.
- 직전 세대는 index를 바꾼 직전 커밋(`35dda989`)의 index를 썼다. 두 세대 경로는 서로 겹치지 않는다(매 갱신마다 내용 해시가 바뀜).

## 바뀐 것
- `build_bilateral.prune_parts(out_dir, manifest, previous)`
  - 64자리 해시 이름 파일만 대상이다.
  - 현재 index와 직전 index에 있는 파일은 보존한다.
- `refresh_pipeline.py`
  - 시작할 때 커밋된 index를 저장해 둔다.
  - `release_gate` 통과 후 한 번만 정리한다.
  - `publish` 안에서 정리하지 않는 이유: 한 실행에서 comtrade와 korea_customs로 두 번 발행하기 때문이다. 그러면 배포 중인 index의 parts까지 지워진다.
- 워크플로의 `git add -- '...commodity_trade_bilateral_v1'`는 삭제도 stage하므로 바꾸지 않았다.
- 테스트 `PrunePartsTest` 추가

## 검증
- `python3 -m unittest discover -s tests` 192개 통과
- `validate_release.py` exit 0
- 삭제 7,168개 전부 `parts/<64hex>.json`이다.

## 다른 PR과의 관계
- #1097(선거 정리) 병합 후 이 PR까지 병합하면 배포 대상은 약 4,200개다.
- #1091(배포할 때만 미등록 parts 제외)과 충돌하지 않는다.
  - 이 PR이 병합되면 #1091은 직전 세대 640개만 업로드에서 뺀다.
  - 둘 다 필요하지는 않다.
- 병합·배포는 사용자가 확정한다. 병합 후 무역 지도에서 칠레 구리 월별 상대국 표가 열리는지(404 없음) 확인한다.
