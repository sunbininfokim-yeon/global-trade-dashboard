# 2026-10-01 정책 수집 GitHub 전환

현재 맥 수집은 유지한다. 원격 활성화 전에 이 변경을 main에 통합해야 한다.

- incremental 전용 `congress.gov:bills:incremental` 상태와 고정 시간 구간, 페이지 offset을 사용한다. bootstrap 상태는 덮어쓰지 않는다.
- 각 페이지를 큐에 저장한 다음 체크포인트를 전진시킨다. Mac의 기존 119대 커서는 이어받고, 회기 범위가 달라진 미완료 커서는 거부한다.
- 수집은 4시간 간격, 119대, 회당 100개 처리 및 최대 100개 임베딩, 탐색 4페이지로 제한한다.
- 수집 작업의 메일 단계는 별도 `POLICY_FAVORITES_MAIL_ENABLED=true` 변수 없이는 실행하지 않는다. 활성화는 이번 범위가 아니다.
- 전환 시 STOP 및 실행 잠금을 확인하고, Mac이 waiting인 경계에서 supervisor를 정상 종료한다. 원격 중복 실행 없음과 메일 변수가 켜져 있지 않음을 확인한 뒤 workflow 활성화 및 incremental dispatch한다.
- 실제 수집/DB 저장 로그를 확인하기 전에는 전환 완료로 보고하지 않는다. 실패 시 원격 예약 비활성화와 실행 종료를 확인한 뒤 기존 Mac 실행 환경으로 복귀한다.

검증: `node --test scripts/lib/congress-incremental.test.cjs` 6개 통과. 운영 전환은 아직 미실행.
