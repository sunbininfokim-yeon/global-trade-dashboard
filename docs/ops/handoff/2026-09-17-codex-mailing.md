# 2026-09-17 메일링 운영 준비

사용자 요청: Pro 전환 후 정책 수집 재개, RSS 저장, 즐겨찾기 정책 변경 메일 구현.

## 구현과 검증

- branch: `claude/mailing-production-20260916`; 09-16 main `6c28325d`에 기존 메일링 변경 통합.
- 법안 단계 변경은 DB 트리거로 보관하고 관측 다음 날 06:00 KST부터 발송 후보가 된다. RSS 보고서는 제목·요약·원문 URL·기관·원자재 태그를 report_id 기준으로 보관한다.
- 정책 상세 링크를 실제 `/policy/us` 경로로 수정했다.
- RSS 적재 이후 기존 발송기가 완료한 건도 claim/발송 직전 기존 receipt를 재확인해 제외한다. 이 검사는 두 발송기의 동시 운영을 허용하지 않는다.
- PGlite SQL/가짜 Resend/browser contract 테스트 40개 통과. 타입 검사 통과. Worker dry-run 빌드는 09-16 통과, 실제 배포는 아님.
- 로컬 RSS snapshot 35건 dry-run 통과, 누락 0건. 아직 운영 DB 저장 아님.

## 운영 상태와 남은 단계

- 09-17 기존 Weekly Commodity Favorites Digest는 active이고 마지막 실행은 09-14 success. 실제 수신함 도착은 확인하지 않았다.
- 정책 GitHub 수집 workflow 두 개는 disabled_manually 유지. 로컬 supervisor는 재시작했으며 기존 체크포인트를 사용한다. 01~02 UTC에는 기존 중복 방지 설정으로 대기한다.
- Supabase Pro는 09-16 인증된 화면에서 확인했다. 09-17 REST 확인 당시 mailing 테이블/함수는 아직 없고, 관리 화면은 다시 로그인이 필요하다.
- 새 SQL은 아직 운영 미적용. SQL 적용 후 RSS archive를 두 번 실행해 중복 없는 저장과 mail_status를 확인한다. 키는 지정된 로컬 env에서 읽고 출력하지 않는다.
- 이 PR은 기존 sender 제거와 UI 배포도 포함한다. 준비 중에는 draft로 두고 main에 병합하지 않는다. 기존 sender를 끄려던 작업은 새 발송기 준비 이전 서비스 중단 위험 때문에 자동 승인 검토에서 거절되었다.
- 새 Worker는 `MAIL_SEND_ENABLED=false`가 기본이다. 실제 발송, 배포, 도메인 검증, 테스트 수신 주소, 테스트 메일 수신 확인은 남아 있다.
- 기존 발송 중지/전환은 준비가 끝난 뒤 별도 승인된 시점에 한다. 운영 mail 상태의 sent/accepted_at는 공급자 접수이며 수신함 도착을 뜻하지 않는다.

적용 파일: `supabase/migrations/20260911010000_mailing_outbox.sql`. 운영 DB에 schema.sql 전체를 실행하지 않는다. 절차와 복구: `services/mailing/README.md`.
