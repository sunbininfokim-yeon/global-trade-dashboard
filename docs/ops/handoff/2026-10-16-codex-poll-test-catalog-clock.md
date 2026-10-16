# 새 주 명부 검토일과 과거 조사 테스트의 날짜 분리

Codex. 사용자 순차 주 보강 중 MT #591에서 발생한 공통 검사 오류 수정. Worktree `/Users/yeoninair/Documents/해운 데이터/us-poll-test-catalog-clock-20261016`, branch `codex/poll-test-catalog-clock-20261016`, base main `0f01e465`.

FL/ME/MN/NC/TX의 최근 원문 검토 테스트가 모든 주 후보 명부를 로딩하면서 정책 검증일을 2026-10-14에 고정했다. 새 MT 공식 명부의10/16 검토일을 읽으면 `ballot review date/source`로 실패한다. 운영 수집기가 아니라 테스트 정책 생성 날짜의 오류다.

기존 공용 `tests.poll_config_fixture.SNAPSHOT_DAY`를 정책 생성에만 사용한다. 실제 normalize/summarize 기준10/14, 원래 수집 영수증·문항 n·수치·7/14 창은 유지한다. 새 회귀는 다른 주 MT 명부를10/16으로 바꿔 다섯 테스트 fixture가 실제로 로딩되는지 및 원래10/14 수집일이 유지되는지 검사한다. 미래 원문 검토를10/14 조사에 적용하는 것은 여전히 거절한다.

주별 packet·감사자료·전국 JSON·운영 코드·UI·workflow 변경 없음. 다주 테스트 변경은 이 공용 기반 PR에만 둔다. 권장 순서: 이 기반 → MT #591 및 같은 오류의 독립 주별 PR. 기반 병합 전 주별 PR base는 packet 없는 이 기반 브랜치를 사용할 수 있다. user만 main 병합/배포 결정. 운영 workflow 직접 실행 안 함.
