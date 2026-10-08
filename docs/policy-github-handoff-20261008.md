# 맥에서 GitHub로 정책 수집 전환 · 2026-10-08

저장소 공개 상태와 main의 독립 incremental 커서를 확인했다. 기존 us-policy-sync 동시성·4시간 스케줄·DB 체크포인트를 유지한다. 본문 색인 단계가 빠져 있어 기존 sync-policy-search.js를 같은 job 마지막에 연결한다. 기본 100문서·20분·DB 6GiB 상한이며 문서당 최대 24개 문단 벡터다. 질의 별칭 확장과 원본 문서 색인 생성은 별개이며 Google 임베딩 API 비용은 발생한다.

RSS는 이미 별도의 Commodity Reports Intel workflow가 4시간마다 생성·mailing_reports 보관을 수행하므로 이 job에 같은 RSS 수집을 중복 연결하지 않는다. 실제 메일 발송 설정은 바꾸지 않는다.

맥 수집기를 대기 경계에서 STOP으로 종료한 뒤 단일 GitHub incremental smoke run(법안 3·공법 1·FR 1·색인 2)을 실행하고 실제 DB 및 로그를 확인한다. GitHub 차단이면 원격 workflow를 다시 비활성화하고 원격 실행 종료를 확인한 후 승인된 맥 수집을 복구한다. 캐시·시크릿은 artifact 또는 Git에 업로드하지 않는다.

## 실제 전환 시험 결과

GitHub run 37734945140(코드 753962a1)은 2026-10-08 14:56~15:02 KST, 5분 51초에 success로 완료했다. 운영 DB data_sync_runs에서 incremental/max_bills=3 실행 및 Congress read/write 3/3, GovInfo Public Law 1/1, U.S. Code 참조 54/54를 확인했다. 본문 색인은 bill:119-hr-10423의 문단 4개, bill:119-hr-10472의 문단 5개(합계 9개)를 실제 저장했다. 즐겨찾기 발송 단계는 skipped다.

Federal Register는 301후보 중 시험 한도 1문서만 처리했으며 저장 0건·남은 300건을 체크포인트에 보존했다. partial은 여기서 남은 배치 대기량을 뜻하며 차단·전량 수집 완료의 증거가 아니다. 다음 정기 배치는 기본 50문서를 이어 처리한다.

맥 PID 802 정상 종료/status=stopped/active_task 없음/STOP=true를 확인했다. GitHub sync-congress workflow는 active, 기본 main 수집 예약은 매 4시간 UTC :17(KST 01:17/05:17/09:17/13:17/17:17/21:17)이다. 본문 색인 단계는 아직 main에 없는 PR #491의 후속 변경이다. 소유권 검사에서 workflow가 Claude 담당으로 분류돼 실패하며 검사 우회는 하지 않았다. 사용자의 이번 수정 예외·병합 승인 응답을 기다린다. 별도 Codex 점검 예약을 재활성화하지 않는다.
