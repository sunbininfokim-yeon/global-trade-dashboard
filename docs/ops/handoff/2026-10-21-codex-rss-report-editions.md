# 같은 주소 보고서의 새 발행본 알림 — Claude 배포 인계

사용자 요청: Codex가 DB/수집 보강을 완료하고 Claude에게 배포 절차를 제공한다.

- checkout: `/Users/yeoninair/Documents/policy-rss-editions-20261021`
- branch: `codex/rss-report-editions-20261021`
- base: `96af0fca` (작업 시작 때 갱신한 origin/main)
- TASKS: `RSS-EDITIONS-20261021`
- 상태: 코드·로컬 SQL 검증 완료 후 PR 검토용. 운영 SQL, merge, Worker/사이트 배포,
  workflow dispatch, 실제 메일 발송은 이 작업에서 수행하지 않는다.

## 문제와 변경

기존 archive는 `mailing_reports.report_id`로 upsert하지만 알림 trigger는 INSERT에만
걸려 있었다. 같은 URL/ID의 다음 발행본은 UPDATE되어 알림이 생기지 않았다.
trigger만 UPDATE로 넓혀도 기존 `commodity_report_notifications(user_id,report_id)`가
새 판까지 차단하므로 적재, 큐 생성, 발송 직전 판별, 접수 기록을 함께 보강했다.

1. 새 migration `supabase/migrations/20261021042059_mailing_report_editions.sql`:
   공식 `report_id + published_at`으로 판을 구별하고 관측 메타데이터를 보관한다.
2. 같은 판의 제목/요약/태그 수정은 새 알림을 만들지 않는다. 아직 선점하지 않은
   해당 판의 큐 내용만 고치며, frozen payload와 발송 이력은 건드리지 않는다.
3. 공급자 접수 시 판별 최소 receipt를 기존 completion 트랜잭션 안에서 기록한다.
   기존 Worker의 RPC 이름, `item_id`, content 필드, idempotency key는 그대로다.
4. 뒤늦은 과거 snapshot이 최신 판을 덮어쓰지 않는다. importer도 중복 ID를 입력
   순서에 관계없이 최신 발행일로 고른다. 같은 배치의 이전 판을 모두 복원하는 기능은 아니다.
5. 늦게 발견한 새 판도 다음 월요일 08:00 KST로 잡는다. 정책 다음날 06:00 KST는 유지한다.
6. 기존 자료는 메타데이터/입증된 접수 이력만 기준점으로 복사한다. 과거 누락분은
   자동 재발송하지 않는다. 8일보다 오래된 신규 적재는 보관만 한다.

운영 `mail_item_active`의 **commodity 중복 판별 한 조건만** 좁게 교체한다.
기존 법안 pause/notify, source opt-out, `policy_idn.mail_item_active(o)` gateway를
보존한다. 정규식이 예상 구조와 맞지 않으면 전체 SQL 트랜잭션이 실패한다.
특별히 인도네시아 migration/함수 전체를 옛 파일로 덮어쓰지 않는다.

## 확인한 운영 상태 — 배포 직전 다시 확인

2026-10-21 읽기 전용 확인:

- 프로젝트: `sjkjjobeahibxgbtomcu`.
- `mailing_reports` 169행, 미선점·미억제 commodity 큐 1행, commodity `sent` delivery 2건.
- 신규 두 표는 아직 없음. `mail_report_archived`는 여전히 AFTER INSERT뿐이다.
- 현재 active 함수 hash: `7349c11f7c583f18c43c09bde041eed8`.
- active 함수에 인도네시아 gateway가 있음.
- 구형 `commodity-digest.yml`: `disabled_manually`. 계속 비활성으로 유지한다.
- 최신 확인 수집 실행: `39514406149`, 2026-10-20 23:20:53 UTC, 전체 workflow success.
  archive 단계는 continue-on-error이므로 전체 success만으로 DB 적재 성공을 확정하지 않는다.
- 메일링 Worker의 현재 ON/OFF·cron은 이번 작업에서 Cloudflare API로 재확인하지 않았다.
  과거 활성 기록을 현재 설정 확인 대신 쓰지 않는다.

## 배포 순서

1. 최신 main에서 PR을 검토하고 로컬 검증을 실행한다. 이 PR에는 UI/Worker/
   `.github/workflows/**` 변경이 없다. migration에 다른 DB 초기화 SQL을 섞지 않는다.

   ```sh
   node --test scripts/lib/policy-mailing-archive.test.cjs services/mailing/test/*.test.mjs
   git diff --check
   ```

   정상 의존성이 설치된 checkout에서 실행한다. 이번 전용 sparse checkout은 공간 절약을
   위해 기존 다른 checkout의 동일 버전 PGlite 의존성을 읽기 전용으로 참조했다.
   `node_modules`나 `supabase/.temp`는 커밋/배포 대상이 아니다.

2. 운영 함수 `mail_capture_report`, `mail_item_active`, `mail_complete`의 본문과
   보고서/발송 trigger 정의를 **비공개 로컬 파일로 백업**한다. 주소·토큰·본문을 PR에 올리지 않는다.
   현재 큐/접수 건수, 실행 중인 sender, 구형 sender 비활성을 확인한다.

3. 아래 migration **한 개만** Supabase migration 도구로 적용하고 이력을 확인한다.
   전체 `schema.sql`, 오래된 메일 migration, 일괄 `db push`를 운영에 재실행하지 않는다.

   ```text
   supabase/migrations/20261021042059_mailing_report_editions.sql
   ```

   20261002 구독 migration 및 notify_enabled가 선행되어야 한다. 인도네시아 모듈은
   선택 사항이다. 적용은 짧은 테이블 잠금과 5초 lock timeout을 사용한다. 잠금/함수 drift
   오류라면 덮어쓰거나 무제한 재시도하지 말고 원인을 확인한다.
   신규 trigger는 운영에 적용되는 순간부터 이후 보고서 저장에 작동한다.

4. SQL 확인 후 PR을 main으로 병합한다. **이번 변경 자체에는 사이트/메일 Worker 재배포가
   필요 없다.** 기존 Worker가 DB의 수정된 함수를 즉시 사용한다. 발송 설정을 다시
   켜거나 Resend Secret을 옮길 필요도 없다. 별도의 Worker 변경이 필요할 때만 담당자가 배포한다.

5. 다음 정상 Commodity Reports Intel 실행의 archive 단계와 DB를 대조한다.
   단순 녹색 workflow 표시 대신 archive 단계 outcome, 신규 판, 큐의 판 키/발송 예정일을 확인한다.
   기존 큐 1행은 변경·재큐잉하지 않는다. 이미 놓친 판의 과거 일괄 재수집·강제 발송도 하지 않는다.
   실제 송신 확인은 다음 정상 예약과 공급자 접수 이력으로 하고, 수신함 도착은 별도 확인한다.

## 적용 직후 읽기 전용 확인

```sql
select to_regclass('public.mailing_report_editions'),
       to_regclass('public.mailing_report_edition_receipts');
select count(*) as observed_editions from public.mailing_report_editions;
select count(*) as accepted_editions from public.mailing_report_edition_receipts;
select kind,count(*) from public.mailing_outbox
where delivery_id is null and suppressed_at is null group by kind;
select pg_get_triggerdef(oid) from pg_trigger
where tgname in ('mail_report_archived','mail_report_keep_latest','mail_report_edition_accepted')
  and not tgisinternal;
select position('policy_idn.mail_item_active' in
  pg_get_functiondef('public.mail_item_active(public.mailing_outbox)'::regprocedure))>0 as indonesia_preserved,
  position('mail_report_edition_sent' in
  pg_get_functiondef('public.mail_item_active(public.mailing_outbox)'::regprocedure))>0 as edition_dedup;
select tablename,rowsecurity from pg_tables where schemaname='public'
  and tablename in ('mailing_report_editions','mailing_report_edition_receipts');
select has_table_privilege('anon','public.mailing_report_editions','select') as anon_metadata,
  has_table_privilege('authenticated','public.mailing_report_edition_receipts','select') as user_receipts;
```

최초 기준점은 점검 당시 최신 보고서 169판에 점검 후 새로 수집한 자료를 더한 수다.
receipt 수는 접수가 확인된 고유 발행본 수이며 delivery 건수와 다르다.
SQL 적용 자체로 outbox가 늘면 안 된다. 동시 수집이 있었다면 생성 사건을 개별 대조한다.

적용 후 Supabase security advisors도 확인한다. 두 표의 browser grant 없음/RLS 활성은
필수다. server-only 표라 browser policy가 없는 INFO는 의도된 상태다.

## 롤백/보존

SQL은 트랜잭션 단위이므로 적용 도중 실패하면 새 정의가 부분 적용되지 않는다.
적용 후 실제 발송 문제라면 먼저 발송을 일시 정지하고 lease/접수 여부를 확인한다.
구형 sender를 켜거나 receipt/큐를 삭제해 재발송시키지 않는다.
필요한 함수 복구는 해당 시점에 백업한 정의와 새로 바뀐 인도네시아 조건을 대조한 뒤
별도 제한 migration으로 한다. 이전 base migration 전체 재실행은 롤백이 아니다.

## 별도 후속 범위

- 날짜 없는 ANRPC 항목을 임의 날짜로 메일링하지 않는다. 발행일 추출은 원문 근거가 필요하다.
- MPOB/VRA 등 수집 성공 후 게시 목록이 0인 경로, 원유/가스 등 태그의 누락·오분류는
  기관별 수집기/분류 사전 검토가 필요하다. 새 판 중복 방지 수정으로 커버리지가 늘었다고 주장하지 않는다.
- 특히 EIA 전력 도매 자료가 gas로 붙는 사례는 별도 분류 검토 대상이다. 해당 태그를
  고치기 전 과거 누락분을 강제로 재큐잉하지 않는다.
- 공식 published_at이 같으면서 파일만 교체되는 기관 개정은 아직 감지하지 않는다.
  시리즈별 판 번호/검증된 파일 지문을 정의한 다음 추가한다.
- PDF 첨부/다운로드 보관은 이번 변경에 포함되지 않는다. 현재 메일은 메타데이터와 원문 링크다.

## 검증 결과

2026-10-21 로컬에서 archive + 메일 전체 66개 통과. 실제 migration을 PGlite 0.5.8에
적용하고 기존 Worker core와 가짜 Resend로 새 판 2회 접수·재시도·구독 해제를 확인했다.
빈 메일 모듈 설치/재실행, 기존 인도네시아 gateway 보존, 미확인 함수 drift 시 전체 rollback,
service-role 쓰기와 browser 역할 차단도 검증했다. 실제 Supabase/PostgREST/Cloudflare 예약
실행 또는 실제 이메일 도착 검증을 대신하지는 않는다.
