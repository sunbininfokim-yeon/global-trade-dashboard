# 2026-09-17 메일링 운영 준비

사용자 요청: Pro 전환 후 정책 수집 재개, RSS 저장, 즐겨찾기 정책 변경 메일 구현.

## 구현과 검증

- branch: `claude/mailing-production-20260916`; 09-16 main `6c28325d`에 기존 메일링 변경 통합.
- 법안 단계 변경은 DB 트리거로 보관하고 관측 다음 날 06:00 KST부터 발송 후보가 된다. RSS 보고서는 제목·요약·원문 URL·기관·원자재 태그를 report_id 기준으로 보관한다.
- 정책 상세 링크를 실제 `/policy/us` 경로로 수정했다.
- RSS 적재 이후 기존 발송기가 완료한 건도 claim/발송 직전 기존 receipt를 재확인해 제외한다. 이 검사는 두 발송기의 동시 운영을 허용하지 않는다.
- PGlite SQL/가짜 Resend/browser contract/API key 검사 총 42개 통과. 키가 없으면 실제 발송 큐를 선점하지 않는 검사 추가. 타입 검사와 Worker dry-run 빌드 통과, 실제 배포는 아님.
- RSS snapshot 35건을 운영 DB에 적재한 뒤 다시 적재했다. 실제 DB 35건, unique ID 35건, 원본 필드 일치 35건을 확인했다. 자동 정기 archive는 아직 운영 workflow에 반영하지 않았다.
- 공통 DB 요청에서도 새 sb_secret 키를 JWT Bearer로 보내지 않도록 수정했다. 로컬 수집기에도 동일 적용. 첫 임베딩 실행은 HTTP 401로 대기했지만 수정 후 별도 제한 실행은 성공했고 NULL 임베딩 대상은 0건이었다. supervisor의 임베딩 lane은 기존 24시간 backoff가 남아 있다.

## 운영 상태와 남은 단계

- 09-17 기존 Weekly Commodity Favorites Digest는 active이고 마지막 실행은 09-14 success. 실제 수신함 도착은 확인하지 않았다.
- 정책 GitHub 수집 workflow 두 개는 disabled_manually 유지. 로컬 supervisor는 재시작했으며 기존 체크포인트를 사용한다. 01~02 UTC에는 기존 중복 방지 설정으로 대기한다.
- Supabase Pro는 09-16 인증된 화면에서 확인했다. 09-17 재조회에서는 mailing 테이블 5개와 mail_status RPC가 이미 존재했다. 기본 구조가 언제 적용됐는지는 현재 증거만으로 확정하지 않는다. 관리 화면은 다시 로그인이 필요하다.
- 09-17 기존 Chrome의 인증 세션을 찾았다. 함수 11개 중 10개의 정규화한 본문 hash가 코드와 일치했고 mail_item_active만 이전 버전이었다. 이 함수만 갱신한 뒤 hash 7829dd28ef7f33e3f346f7f94da149b5 일치를 확인했다. 메일링 테이블 5개 모두 RLS가 켜져 있고 mail_* 함수의 anon/authenticated 실행 권한 노출은 0개, 변경 감지 트리거 3개 모두 활성 상태다. 지정 테스트 계정의 인증 완료도 boolean으로 확인했다. 큐 pending/overdue 0, states {}, DB 455978131 bytes였다.
- 이 PR은 기존 sender 제거와 UI 배포도 포함한다. 준비 중에는 draft로 두고 main에 병합하지 않는다. 기존 sender를 끄려던 작업은 새 발송기 준비 이전 서비스 중단 위험 때문에 자동 승인 검토에서 거절되었다.
- 새 Worker는 `MAIL_SEND_ENABLED=false`가 기본이다. 로컬 Cloudflare OAuth 인증은 유효하고 해당 Worker는 아직 존재하지 않는다. 미리보기 배포에 Supabase 두 Secret만 요구하도록 설정했고 실제 발송은 코드에서 Resend 키를 필수 확인한다. 실제 배포 요청은 Supabase 서비스 롤 키를 Cloudflare Secret으로 전달하는 데 명시적 승인이 필요하다는 자동 검토 거절로 미실행이다. 사용자 질문에 각 서비스 역할을 설명했고 승인은 아직 대기 중이다.
- 테스트 수신 주소는 사용자로부터 받았다. Resend 도메인 조회를 위한 Google 로그인은 별도 접근 승인이 없다는 자동 검토 거절로 미실행이다. 사용자에게 로그인/조회 승인을 요청했다. 키 값을 채팅에 받지 않는다. 실제 메일 발송은 아직 하지 않았다.
- 기존 발송 중지/전환은 준비가 끝난 뒤 별도 승인된 시점에 한다. 운영 mail 상태의 sent/accepted_at는 공급자 접수이며 수신함 도착을 뜻하지 않는다.
- 사용자 명시적 승인 후 브랜치를 업로드하고 draft PR #321을 생성했다. cbeaa734 기준 GitHub의 Mailing Reliability Checks와 Ownership guard는 모두 통과했다. main 병합이나 기존 메일링 중지는 하지 않았다.

적용 파일: `supabase/migrations/20260911010000_mailing_outbox.sql`. 운영 DB에 schema.sql 전체를 실행하지 않는다. 절차와 복구: `services/mailing/README.md`.
