# 맥에서 GitHub로 정책 수집 전환 · 2026-10-08

저장소 공개 상태와 main의 독립 incremental 커서를 확인했다. 기존 us-policy-sync 동시성·4시간 스케줄·DB 체크포인트를 유지한다. 본문 색인 단계가 빠져 있어 기존 sync-policy-search.js를 같은 job 마지막에 연결한다. 기본 100문서·20분·DB 6GiB 상한이며 문서당 최대 24개 문단 벡터다. 질의 별칭 확장과 원본 문서 색인 생성은 별개이며 Google 임베딩 API 비용은 발생한다.

RSS는 이미 별도의 Commodity Reports Intel workflow가 4시간마다 생성·mailing_reports 보관을 수행하므로 이 job에 같은 RSS 수집을 중복 연결하지 않는다. 실제 메일 발송 설정은 바꾸지 않는다.

맥 수집기를 대기 경계에서 STOP으로 종료한 뒤 단일 GitHub incremental smoke run(법안 3·공법 1·FR 1·색인 2)을 실행하고 실제 DB 및 로그를 확인한다. GitHub 차단이면 원격 workflow를 다시 비활성화하고 원격 실행 종료를 확인한 후 승인된 맥 수집을 복구한다. 캐시·시크릿은 artifact 또는 Git에 업로드하지 않는다.
