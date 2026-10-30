# 과거 조사와 최신 명부 검증 시각 분리

- 담당: Codex, worktree `/Users/yeoninair/Documents/해운 데이터/us-ne-research-integration-20261020`.
- 브랜치 `codex/poll-historical-catalog-clock-20261021`, 시작 main `96af0fca70f0e9b598e7d0f909a8205e19426420`.
- NE #647의 10/20 명부를 새 main에 합치면 과거 10/18 조사 테스트들이 최신 전체 주지사 명부를 과거 날짜로 검사해 `Future governor candidate review`가 발생했다. 최초 합본에서 65개 오류가 이 패턴이었다. 마지막 재생 1개 오류는 검증 실행 중 checkout 전환이 있었으므로 증거로 사용하지 않으며 고정된 최종 checkout에서 재검증한다.
- 18개 공용 테스트의 실제 운영 catalog 로딩에만 기존 `SNAPSHOT_DAY`를 사용한다. 과거 조사 `DAY`, normalize/summarize 날짜, 문항 수치, 검토일, 미래 원문 거부 검증은 유지한다. 로컬 잘못된 명부 fixture의 의도적인 미래 날짜 검사는 변경하지 않는다.
- 집중51개 통과: AR·정당 의뢰·IA·CO·VA·catalog·주지사 경계 검사. 공용 snapshot helper는 운영 JSON이나 수집시각을 쓰지 않는다.
- 후속 #644 → #649 → #647 순서는 유지한다. 이 공용 테스트 기반은 #647에 앞서 반영한다. NE packet/원문과 함께 넣지 않는다. 최종 합본 검사 결과는 별도 종료 인수에 기록한다.
- UI·workflow·공용 수집기·주별 입력·전국 JSON 수정 없음. 병합·배포·운영 workflow dispatch 없음.
