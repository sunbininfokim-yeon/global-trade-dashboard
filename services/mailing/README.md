# 메일링 운영 계약

2026-09-11 구현. 기존 Resend를 유지한다. 기본 발송 설정은 `false`다. 09-17 운영 DB 함수와 트리거를 확인하고 RSS 중복 방지 함수를 갱신했다. 09-20 `chokemonitor-mailing` Worker를 발송 OFF로 배포했고, 실제 cron preview 실행을 확인했다(초기 version `16998c26-bd28-4a26-820a-88e0ba33a764`). Resend 루트 도메인 인증과 키 연결은 완료했으며 실제 발송은 아직 하지 않았다.

Supabase는 보고서·변경 사건·발송 이력을 저장하고, Cloudflare Worker는 예약 시간에 발송 후보를 선별해 Resend API를 호출한다. 실제 이메일 발송 서비스는 계속 Resend다. Worker의 미리보기 배포에는 Supabase 연결 정보만 필요하다. 발송을 켤 때는 Resend 키도 필요하며, 키가 없으면 대기열을 선점하기 전에 실패한다. GitHub 배포 workflow는 세 키 모두를 요구한다.

## 두 경로

| 기능 | 저장과 발송 | 기본 시간 (한국 시간) |
| --- | --- | --- |
| 즐겨찾기 법안 | `bills.current_stage` 변경 트리거 → `mailing_outbox` → 수신자별 delivery → Resend | **DB에서 변경을 확인한 다음 날 06:00**부터, 06:10~06:50 재시도 |
| 원자재 RSS/공식 보고서 | 기존 수집기의 JSON → `mailing_reports` → 즐겨찾기 원자재/기관 설정으로 선별 → delivery → Resend | 기존 **월요일 08:00** 유지 |

EO 즐겨찾기는 공식 요약의 내용이 달라질 때 정책 알림에 포함한다. 단순 `updated_at` 변경은 알리지 않는다. RSS는 기존 원자재 공식 보고서 서비스이며, 모든 뉴스 RSS를 새로 구독시키는 기능이 아니다.

Worker는 10분마다 실행한다. 06시대에는 정책 메일에 전체 처리량을 할당한다. 07시 이후에도 남은 실패 건을 재시도하므로 오류 발생 시 늦은 메일을 버리지 않는다. 소스의 실제 사건일과 DB 관측일은 다르다. Congress 수집 지연, 잘못 저장된 단계, 플랫폼/Resend 장애, 수신 서버 지연은 이 발송기만으로 해결되지 않는다. **07시 전 inbox 도착을 보장한다는 뜻은 아니다.**

## 상태와 중복 방지

- DB의 법안 업데이트와 알림 생성은 한 트랜잭션이다. 같은 날 두 번 바뀌어도 두 사건을 보존한다. 즐겨찾기 등록 자체는 알리지 않는다.
- `mailing_outbox(user_id,event_key)`가 사건 중복을 막는다. 보고서는 `mailing_reports.report_id`가 기본키다. 기존 `commodity_report_notifications`는 적재 시점뿐 아니라 큐 선점과 발송 직전에도 읽는다. 새 큐에 쌓인 뒤 기존 발송기가 보낸 보고서도 전환 후 재발송하지 않는다. 두 발송기의 동시 운영을 허용한다는 뜻은 아니다.
- 첫 RSS 적재는 설치 시점 기준 8일 안의 보고서만 알림 후보로 만든다. 이후 큐에 들어간 항목은 8일이 지나도 소실되지 않는다. 원문 전문/PDF 대신 제목·600자 요약·URL·태그만 저장한다.
- `mail_claim`은 `FOR UPDATE SKIP LOCKED`, 5분 lease, 매번 새 token을 쓴다. 한 delivery는 최대 20개 사건이다. Worker 한 번에 최대 5 deliveries, 현재 06시대 최대 30 deliveries다. 이용자/변경량 증가 시 이 용량과 실제 무료 플랜 한도를 재검토해야 한다.
- 수신자는 `auth.users.email_confirmed_at`이 있는 계정 이메일만 쓴다. 사용자가 자유롭게 수정하는 `profiles.email`은 수신 주소가 아니다.
- 발송 직전에도 즐겨찾기·수신 설정·현재 인증 이메일을 재확인한다. 채널별 설정은 DB와 Auth API에서 독립 저장하며 원자재의 기존 기관 필터를 유지한다. 최신 main의 계정 일시정지·항목별 알림·기관 필터 UI를 보존하며, 채널별 새 스위치 UI는 이번 배포 준비 범위에서 제외한다.
- 첫 요청의 전체 payload와 `mailing/<delivery_id>` idempotency key를 고정한다. 템플릿이 바뀌거나 DB 성공 응답을 잃어도 같은 payload/key로 재시도한다. 성공은 수신자마다 즉시 기록한다.
- 네트워크·408/425/429/5xx는 재시도, 429는 Retry-After 준수. 401/403은 실행을 중단한다. 모호한 발송의 첫 시도 이후 23시간이 지나면 `uncertain`으로 격리한다. Resend의 키 보존 시간이 24시간이므로 그 이후 자동 재발송은 하지 않는다.
- `state='sent'`/`accepted_at`는 **Resend API 접수 성공**이다. 수신함 도착, 반송, 스팸 분류는 확인하지 않는다. 해당 판정에는 Resend delivery 로그 또는 별도 webhook 연동이 필요하다.
- 브라우저는 서버용 테이블/발송 RPC를 호출할 수 없다. Worker HTTP 요청은 항상 404이며, 발송을 호출하는 공개 URL이 없다.

## 적용 순서

1. 준비 단계에서는 기존 발송 workflow를 유지하고 새 발송은 `false`로 둔다. DB 구조 적용·RSS 적재·로컬 검증은 메일을 보내지 않는다. 기존 sender 중지는 새 발송기의 준비를 검증한 다음 승인된 전환 단계에서만 한다. 특히 기존 법안 sender는 새 outbox의 발송 기록을 이해하지 못한다.
2. 기존 DB의 `profiles`, `user_favorites`, `bills`, `executive_orders`, `commodity_digest_source_prefs`, `commodity_report_notifications`를 확인한다. 사용자/즐겨찾기 마이그레이션과 `20260904_favorite_commodity_kind.sql`, `20260904_commodity_report_notifications.sql`, `20260904_commodity_digest_source_prefs.sql`이 선행돼야 한다. 운영 DB를 초기화하거나 schema.sql 전체를 다시 실행하지 않는다.
3. 새 DB에는 `20260911010000_mailing_outbox.sql` → 계정/즐겨찾기 알림 컬럼 마이그레이션 → `20260920020000_mailing_bill_lifecycle.sql` → `20261002010000_mailing_bill_event_identity.sql` → `20261002020000_mailing_subscription_preferences.sql` 순서로 적용한다. 이미 최신 함수가 있는 운영 DB에는 초기 메일 SQL만 재실행하지 않는다. SQL은 재실행 가능하며 과거 법안 사건을 소급 생성하지 않는다. 이 파일이 메일링 DDL의 정본이다. `schema.sql`은 정책 모듈 설치본으로, 계정·즐겨찾기·메일링까지 포함한 전체 앱 설치본이 아니다.
4. 2026-10-04 수정본은 최신 main의 UI·기존 sender·워크플로를 보존한다. PR 병합과 실제 발송 전환은 별개다. 기존 `commodity-digest.yml`과 Congress의 `POLICY_FAVORITES_MAIL_ENABLED`를 확인하고, 전환 승인 뒤 기존 sender를 중단해 실행 중인 발송이 없음을 확인한 다음 Worker를 활성화한다. 기존 sender는 새 outbox를 이해하지 못하므로 두 발송기를 동시에 켜지 않는다.
5. 로컬에서 기존 JSON을 적재하거나 `Commodity Mailing Archive Recovery`를 실행한다. 로컬 환경 파일은 인자로 로드하며 키 값을 출력하지 않는다.

   ```bash
   # 저장소 루트. 검사는 네트워크/쓰기 없이 실행 가능.
   node scripts/archive-mailing-reports.js --dry-run
   # SQL 적용 이후: 보고서 보관과 큐 생성. 메일은 발송하지 않음.
   node --env-file=/Users/yeoninair/Documents/global-trade-dashboard-local/.env.local scripts/archive-mailing-reports.js
   # 읽기 전용 상태 확인. --dry-run은 env가 true여도 발송을 금지한다.
   node --env-file=/Users/yeoninair/Documents/global-trade-dashboard-local/.env.local scripts/notify-favorites.js --dry-run
   ```

6. `Deploy Mailing Worker`를 main에서 **send_enabled=false**로 실행한다. GitHub의 `CLOUDFLARE_API_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`를 사용한다. 임시 파일(0600)로 Worker secret을 전달하고 삭제한다. `inputs.send_enabled`를 그대로 검증·전달하며 `||`로 덮어쓰지 않는다.
7. Cloudflare cron 실행과 preview 로그, Supabase 큐, Resend 발신 도메인 `chokemonitor.com`의 검증 상태/현재 quota를 확인한다. 별도 테스트 수신 주소에 대한 발송은 명시적 허가 후 확인한다. 발신 기본값은 `alerts@chokemonitor.com`이다.
8. 승인된 운영 전환 시 기존 sender의 실행 종료와 제거를 확인한 후 같은 workflow를 **send_enabled=true**로 실행한다. 기존 발송 workflow를 재활성화하지 않는다. cron 변경 전파 시간까지 고려해 06시 직전에 전환하지 않는다. 기존 발송 중지는 준비가 끝나기 전에 선행하지 않는다.

**롤백:** 같은 workflow를 `false`로 실행해 예약 발송을 멈춘다. SQL/큐를 삭제하지 않는다. 기존 sender를 그냥 되돌리면 서로 다른 중복 방지 기록 때문에 중복이 생길 수 있다. 이미 시작한 네트워크 요청은 설정 변경으로 회수할 수 없다.

## 점검과 장애 복구

```sql
-- SQL Editor / service role 전용. 주소/본문을 출력하지 않는 집계.
select public.mail_status();
select state, count(*) from public.mailing_deliveries group by state;
select kind, min(due_at), count(*) from public.mailing_outbox
where delivery_id is null and suppressed_at is null group by kind;
select pg_size_pretty(sum(pg_total_relation_size(c.oid))) as mailing_storage
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relkind='r' and c.relname like 'mailing_%';
```

`policy_past_7am>0`, `uncertain`, `failed`는 Worker 경고에도 남는다. 현재 경고는 Cloudflare 로그이며 운영자에게 별도 메일/SMS를 보내는 모니터링은 아니다. 완료 이력과 최소 중복 방지 키는 유지한다. 대규모 운영 전에는 주소/본문의 보관 기간과 DB 용량 정책을 별도로 정해야 한다.

`uncertain`은 자동 재시도시키지 말고 Resend에서 해당 idempotency key/요청의 접수 여부를 대조한다. 접수됨을 확인하면 provider message id와 접수 시각으로 DB 상태를 정정하고, 접수되지 않았다는 증거가 있을 때만 수동 재시도를 결정한다. 키만 새로 만들어 재발송하지 않는다.

RSS 적재 실패 시 workflow가 실패하며 `commodity-mailing-recovery` artifact에 그 실행의 JSON을 14일 보관한다. 해당 artifact를 내려받아 아래 importer의 `file`로 넣으면 부분 저장 이후에도 report_id 기준으로 재개한다. 현재 JSON에 남아 있는 보고서는 매일 recovery workflow가 다시 적재한다. **artifact까지 만료되고 원본에서 사라진 보고서는 복원되지 않으므로 archive 실패를 방치하지 않는다.**

```js
// Node, repo root, 승인된 env 파일을 로드한 상태. 경로는 받은 artifact로 교체.
const {archiveReports} = require('./scripts/archive-mailing-reports');
archiveReports({file: '/path/to/commodity_reports_v1.json'}).then(console.log);
```

## 검증

```bash
cd services/mailing
npm ci
npm test                 # PGlite에서 실제 SQL 실행 + 가짜 Resend + browser Auth contract
npm run types
npm run check
npm run build            # wrangler deploy --dry-run; 실제 배포 아님
```

테스트는 운영 PostgreSQL/Supabase/PostgREST, Cloudflare cron, 실메일 수신 확인을 대신하지 않는다. 운영 적용과 실제 수신 검증은 아직 별도 단계다.

공식 근거: [Resend idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys), [Cloudflare Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/), [Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/), [GitHub scheduled workflow delays](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).


## 2026-09-20 입법 이력 계약 보강

PR #339 수집기가 `bills.raw_source.lifecycle`에 원·단계·최신 사건·표결·다음 확인 단계를 넣는다.
`20260920020000_mailing_bill_lifecycle.sql`을 기존 outbox migration 뒤에 적용하면
상위 단계 코드가 같아도 새 절차 표결을 별도 사건으로 보존한다. 처음 넣는 canonical
스냅샷은 조용히 기준점으로 삼는다. 같은 이력 재수집·라벨 변경은 알림을 추가하지 않는다.
전체 자식 행을 다시 조회하지 않고 같은 bill 업데이트 안의 스냅샷을 읽는다.

템플릿은 하원/상원 출발, 현재 원별 단계, 토론 종결과 법안 통과 구분, 찬반 수,
근거 날짜·안전한 공식 링크, 다음 확인 항목을 표시한다. 기존 payload와도 호환된다.
44개 테스트(PGlite 실제 SQL 포함), tsc, Worker dry-run 통과. 후속 migration을 운영 SQL Editor에 적용하고 Saved를 확인했다. 템플릿과 Resend 키를 연결한 version `bf61656d-4a31-4682-af8e-e1d66d6ef03a`도 발송 OFF로 배포했다. 정책 수집기의 새 snapshot 생성 코드는 PR #339에 있으며 활성 recovery 수집기에는 아직 옮기지 않았다.

발신 도메인은 사용자 정정에 따라 `chokemonitor.com` / `alerts@chokemonitor.com`이다.
사용자가 복구한 root 도메인 `chokemonitor.com`은 Resend API에서 verified,
region ap-northeast-1, sending enabled 및 DKIM/SPF verified로 확인했다.
기존 DNS를 덮어쓰지 않았다. `mail.chokemonitor.com`은 사용하지 않는다.
Resend 키는 Worker 비공개 Secret에 연결했고 URL/관리키를 포함한 세 Secret의 이름만 확인했다.
최신 공개 `public/data/commodity_reports_v1.json`(2026-09-20 05:20 UTC)의 37건을
검증 후 DB에 보관했다. `/api/commodity-reports`는 화면용 windows 구조이므로 importer 입력으로 쓰지 않는다.
대기열은 pending 1, overdue 0이며 실제 발송은 OFF다. 테스트 메일 1건은 본문을 준비하고 별도 승인을 요청했다.


## 2026-10-07 수요일 배포 준비

- 최신 main과 충돌하던 UI·즐겨찾기·incremental 설정은 main을 보존한다. #321의 기본 DDL·서비스와 #443 보강을 함께 검증한다.
- `npm test`의 설치 테스트는 비어 있는 PGlite에 앱 필수 테이블을 만든 뒤 실제 메일 마이그레이션을 순서대로 적용한다. Supabase 전체 프로젝트·pgvector 스키마 설치를 검증한 것은 아니다.
- Worker를 ON으로 바꾸기 전 기존 GitHub sender 중단, 실행 중인 sender 0개, 도메인 인증과 서비스 Secret을 확인한다. `MAIL_SEND_ENABLED=true`가 실제 예약 발송을 켜는 설정이다. 이 변경은 별도 승인된 전환 단계에서만 실행한다.
- 등록된 테스트 계정으로 공급자 접수와 실제 수신함 도착을 확인한다. 단순 `sent` 기록은 수신함 확인이 아니다.
- 실패 시 Worker OFF로 복귀하고 기록·고정 idempotency key를 보존한다. 불확실한 전송을 수동으로 다시 보내지 않는다.
- 맥 법안 수집 4시간 주기와 `scripts/sync-mailing-reports-local.js`를 연결한다. 원본 기관 피드를 직접 읽으며 제목·요약·태그·공식 URL을 DB에 보관한다. 원본 PDF 파일 저장과 웹사이트 JSON 배포는 별도다.
- 원자재 분류는 키워드·보고서 시리즈 사전·기관 문맥 규칙이고, Gemini는 일부 제목 번역/주석을 보조한다. 미분류 항목·발행일 불명은 메일 후보로 강제 전환하지 않는다.
