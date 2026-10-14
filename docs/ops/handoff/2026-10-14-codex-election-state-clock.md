# 주별 evidence 하위 CLI의 검증 시계

WA 검증 재개 중 #540이 병합된 최신 main `74be3734205aee112cfe3a5c4dd912cf3a198a15`에서도 `publish_packet_projections.py`의 실제 하위 명령이 실패함을 재현했다. 담당 checkout은 `/Users/yeoninair/Documents/해운 데이터/us-election-state-clock-20261014`, branch는 `codex/election-state-clock-20261014`다. 다른 세션의 UI/ME checkout은 수정하지 않았다.

상위 projection은 현재 명부 검토 시계를 사용하지만 `refresh_state_evidence.py --as-of 2026-10-11`은 여전히 전국 연방·주지사 명부를 과거 관측일로 검증했다. WA의 10/13 후보 검토가 다른 주의 과거 재생성을 막았다. 이 CLI도 기존 `validation_day`로 현행 명부를 검증하되 `build_state`, 관측 창, 원래 receipt/as_of/fetched_at은 사용자가 지정한 관측 시계를 그대로 쓴다. 실제 현재 UTC일보다 미래인 검토는 계속 거절한다.

#540 이후 main에 병합된 AK/KS 테스트 두 파일도 정책 로딩에 고정 역사 날짜를 사용하고 있었다. 기존 `SNAPSHOT_DAY`를 그 정책 검증에만 적용하고, 해당 주의 10/9 조사 수치·원문 검토·과거 창 시나리오는 변경하지 않았다.

새 회귀 3개는 mock 처리한 상위 subprocess에 의존하지 않고 실제 하위 CLI와 전체 현행 명부 검증·state builder를 실행한다. 타주 연방/주지사 검토가 늦어져도 CT의 기준일·영수증·poll window가 유지되고, 실제 미래 검토에서는 게시 함수를 호출하지 않는지 확인한다. 임시 검증 사본에서 WA 입력을 포함한 `publish_state_packets.py --pending` 및 전체 `publish_packet_projections.py`도 실행했다. 네트워크 재수집이나 새 수집일 생성이 아니다.

공용 수정만 별도 PR로 분리한다. 주별 packet·전국 생성 JSON·공용 검토 목록·workflow·UI·LETF·TASKS 변경은 없다. WA는 이 기반에서 독립 PR을 만들며 ME 등 다른 주 PR 위에 쌓지 않는다. 기반 병합 후 state PR의 base를 main으로 바꾸고 재검증한다. 병합·배포·운영 workflow 실행은 사용자 결정이다.

검증 사본의 WA 입력 포함 통합 polling 465개, 금융 68개, 연방 명부 6개, 선거 JS 51개 및 소유권 회귀 9개 통과. finance 지도는 2026 레이스576/후보기록4,857/원공시기록16,651 대조 통과, deploy-chain39개 연결 통과. 새 하위 CLI 회귀3개도 모두 통과했다. 원본 public JSON5,241개는 변경하지 않았다. 이 수치는 검증 사본에서 WA를 포함한 결과이며 PR 자체에 WA 입력을 포함하지 않는다. GitHub 검증 결과는 PR에서 별도 확인한다.
