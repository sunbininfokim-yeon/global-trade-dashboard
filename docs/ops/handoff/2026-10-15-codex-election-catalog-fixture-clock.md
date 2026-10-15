# 현행 governor 명부 검증 테스트의 시계 후속 보완

#554는 fbe255ba에서 병합됐다. OR 입력의 통합 검증 중 CT governor ballot 목록 검사 하나가 전국 현행 목록을 여전히 역사적 시나리오 DAY=2026-10-09로 검증해 실패함을 재현했다. 최신 main에 새로 병합된 WA 테스트도 정책 로딩에서 DAY=2026-10-13을 사용해 같은 원인의 오류가 발생했다. 이 후속 변경은 CT 목록 검증 호출 세 곳과 WA 정책 로딩 두 곳만 기존 SNAPSHOT_DAY로 맞춘다. CT/WA 조사 원문, 역사적 7/14일 창, 운영 수집 코드와 실제 수집일은 바꾸지 않는다.

담당 checkout은 `/Users/yeoninair/Documents/해운 데이터/us-election-state-clock-20261014`, branch는 `codex/election-catalog-fixture-clock-20261015`다. 최신 main 57941ec0722940966abfe6c077d4c34db76efd7c에서 독립 공통 PR을 만든다. 주별 packet, 전국 산출물, 공용 검토 목록, UI/workflow/LETF/TASKS는 포함하지 않는다. OR 주별 입력은 이 packet 없는 공통 기반에서 별도 PR로 검토한다.

2026-10-15 검증 사본에서 OR의 10/14 검토를 포함한 CT 테스트 14개를 통과했다. 원래 과거 window가 빈 결과를 유지하는 검사와 미래·변경 문서 보류 검사도 포함된다. 이는 새 네트워크 수집이 아니다. 전체 통합 검증과 GitHub 검사는 OR 인수 문서 및 각 PR에서 별도로 기록한다. 병합·배포·운영 workflow 실행은 하지 않는다.

GitHub에서 OR 포함 #579는 491개/JS 74개가 통과했으나, OR가 없는 이 공통 PR은 NC 금융 신원 테스트의 `future state polling snapshot` 오류 1건으로 실패했다(481개 실행). `PUBLIC_SNAPSHOT_DAY`가 전역 as_of와 명부 검토일만 고려하고 개별 레이스의 더 최신 수집 기준일은 빠뜨린 것이 원인이었다. OR의 governor 검토일이 10/14로 늦어지면 우연히 테스트 시계도 늦어져 이 오류가 가려졌다. 공통 fixture는 현행 명부·전역/레이스별 관측 기준일의 최댓값을 사용하도록 고치고, fetched_at을 관측일로 바꾸거나 원본 board/receipt를 수정하지 않는 경계를 회귀 3개로 확인한다. OR 입력을 제외한 공통 기반만 별도 사본에서 검증한다.
