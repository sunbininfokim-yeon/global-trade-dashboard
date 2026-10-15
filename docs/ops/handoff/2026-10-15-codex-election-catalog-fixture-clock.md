# 현행 governor 명부 검증 테스트의 시계 후속 보완

#554는 fbe255ba에서 병합됐다. OR 입력의 통합 검증 중 CT governor ballot 목록 검사 하나가 전국 현행 목록을 여전히 역사적 시나리오 DAY=2026-10-09로 검증해 실패함을 재현했다. 이 후속 변경은 해당 테스트의 목록 검증 호출 세 곳만 이미 사용하는 SNAPSHOT_DAY로 맞춘다. CT 조사 원문, 역사적 7/14일 창, 운영 수집 코드와 실제 수집일은 바꾸지 않는다.

담당 checkout은 `/Users/yeoninair/Documents/해운 데이터/us-election-state-clock-20261014`, branch는 `codex/election-catalog-fixture-clock-20261015`다. 최신 main 57941ec0722940966abfe6c077d4c34db76efd7c에서 독립 공통 PR을 만든다. 주별 packet, 전국 산출물, 공용 검토 목록, UI/workflow/LETF/TASKS는 포함하지 않는다. OR 주별 입력은 이 packet 없는 공통 기반에서 별도 PR로 검토한다.

2026-10-15 검증 사본에서 OR의 10/14 검토를 포함한 CT 테스트 14개를 통과했다. 원래 과거 window가 빈 결과를 유지하는 검사와 미래·변경 문서 보류 검사도 포함된다. 이는 새 네트워크 수집이 아니다. 전체 통합 검증과 GitHub 검사는 OR 인수 문서 및 각 PR에서 별도로 기록한다. 병합·배포·운영 workflow 실행은 하지 않는다.
