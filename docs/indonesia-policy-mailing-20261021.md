# 인도네시아 상품·지역 메일 연결 (2026-10-21)

[다중 상품·지역·전국 구독 보강](indonesia-policy-multi-scope-mailing-20261021.md): 13개 상품 다중 체크·38개 주와 기존 군/시·전국 선택, 원자 저장, 전국/지역 겹침의 메일 중복 방지를 추가했다. 운영 DB 적용 완료, UI는 Claude 배포 대상이다.

[최신 운영 보강](indonesia-policy-collector-coordination-20261021.md): 호스트 간 수집 잠금·실행 상태·메타데이터/잘린 본문의 메일 자동 보류를 추가했다. 현재 73문서/83버전·불완전 원문 보류 2건·구독/발송 대기 0건, 메일 검사는 60개다. 아래의 최초 적용 수치와 후속 운영 점검을 구분한다. 상시 예약·발송은 계속 꺼져 있다.

[수집·저장 기본 구조](indonesia-policy-refresh-hardening-20261021.md): 다운로드→DB 실행기와 원문 보존·문서별 동시 저장 guard.

## 반영 상태

운영 Supabase에 인도네시아 전용 구독·기준선·변경 후보와 Auth RPC를 적용했다. 기존 73문서의 기준선 73건, 구독 0건·변경 후보 0건·IDN outbox 0건을 확인했다. **IDN `delivery_enabled=false`이며 실제 메일은 보내지 않았다.** 검색 UI와 메일 Worker 코드는 이 PR의 Claude 검토·병합·배포 대상이다. 사이트에 구독 UI가 배포됐거나 인도네시아 메일이 가동 중이라는 뜻이 아니다.

기존 미국 문서·즐겨찾기 데이터는 건드리지 않는다. `policy_idn`에는 IDN 자료·구독만 보관하고 기존 공통 발송 대기열에는 새 `item_kind=idn_policy`를 사용한다. `kind=policy` 운송 경로만 공유해 기존 다음 날 06:00 KST 계산·lease·Resend idempotency·재시도·수신 주소 검증을 재사용한다. 기존 `policy_enabled` 수신 거부는 IDN에도 적용된다. 미국 법안 일시정지는 IDN 구독과 별개다.

## 구독 및 변화 처리

- 검색과 분리된 접힌 패널에서 로그인한 이용자가 상품·지역 조합을 저장하거나 해제한다. 지역 선택은 확보한 지방 발행 관할 목록이다. 기업 이름·사업 목적·개인 이메일은 공개 UI/저장소에 넣지 않는다.
- 동일 사용자의 상품·지역 조합은 한 행이며, 비활성→활성 전환마다 구독 세대를 갱신한다. 과거 구독의 미발송 항목이 재가입으로 되살아나지 않는다. 구독 최대 30개이며 확인된 Auth 이메일이 필요하다.
- 버전이 새로 저장되면 동일 트랜잭션에서 변경 **후보**를 기록한다. 기존 자료·더 오래된 관측 버전은 조용히 유지한다. 신규 문서도 후보가 되며 최초 수집을 법적 제정 시점으로 단정하지 않는다. 동일 버전 재저장은 중복 후보를 만들지 않는다.
- 검토자는 해당 버전의 정확한 원문 인용·공식 URL·상품·적용 범위·변화 설명을 지정한다. 단순 해시/OCR 변화는 자동으로 개정·폐지가 되지 않는다. 미검토 후보는 발송하지 않는다.
- 검토된 전국 적용 자료는 지정 상품이 맞는 구독에 포함한다. 지정 지역 적용 자료는 상품 **AND** 지역이 일치해야 한다. 중앙 발행 규정도 적용이 일부 지역이면 그 지역에만 보낸다. 지방 문서를 전국 적용으로 지정하거나 군·시→주 관계를 추정하는 것은 거부한다.
- 같은 사용자의 여러 상품/지역 조건이 한 이벤트에 걸리면 알림 한 건으로 묶는다. 이벤트 발견 뒤 가입한 구독자는 제외한다. 발송 게이트가 켜져 있으면 **검토 완료와 같은 트랜잭션에서 대기열을 자동 생성**한다. 활성화 이전 후보를 사후 발송하지 않는다. 별도 enqueue 명령은 집계·멱등 재처리용이다.
- 발송 직전 원본 이벤트의 검토/보류·구독 세대·구독 해제·전체 정책 수신 거부·운영 게이트를 다시 확인한다. 검토를 철회하면 pending/재시도 항목도 보류된다. 이미 공급자에게 접수된 요청은 회수할 수 없다.

## 권한·마이그레이션

`20261020174850_indonesia_policy_mailing.sql` → `20261020213953_indonesia_mail_auth_gateways.sql` → `20261020214317_indonesia_mail_review_enqueue.sql` 순서다. 선행 IDN corpus/isolation 및 메일링 migrations가 필요하다. 새 DB는 `schema.sql` 단독이 아니라 해당 선행 migration부터 순서대로 적용해야 한다. 설치·재적용 검사는 실제 SQL을 실행한다.

`policy_idn`의 Auth 직접 접근은 계속 금지한다. 공개 `idn_my_mail_subscriptions`, `idn_set_my_mail_subscription`는 SECURITY INVOKER다. 실제 권한 처리는 비공개 `policy_idn_user`의 `auth.uid()` 확인 함수로 제한한다. 사용자 ID를 입력받지 않으며 다른 사용자의 구독은 조회·변경할 수 없다. 검토·대기열·게이트 함수는 service_role만 호출한다. 구독은 profiles 삭제에 따라 삭제된다.

보안 Advisors를 확인한 뒤 새 공개 SECURITY DEFINER 경고를 제거했다. 서비스 전용 private 기준선/변경/설정 테이블의 RLS 정책 없음 INFO는 의도된 기본 거부다. 이를 없애려고 공개 읽기 정책을 만들지 않는다. 기존 프로젝트의 다른 경고를 이번 기능이 해결했다고 주장하지 않는다.

플러그인의 `apply_migration`은 요청 만료 오류로 두 번 실패했고 미반영을 확인했다. 이후 SQL 실행 경로로 적용·검증하고, 동일 SQL과 버전을 `supabase_migrations.schema_migrations`에 기록했다. 적용 전 기존 함수·제약·집계는 비공개 로컬 `policy-downloads/indonesia-20261021/mailing/pre-migration.json`에 보관했다. 키·수신 주소는 백업/보고서에 넣지 않았다.

## 검토 운영 명령

```bash
# 읽기 전용: 발송 설정과 최대 20개 후보의 ID·원문 링크
node scripts/indonesia_policy/mail-review.cjs --env-file /ABS/ENV
# JSON 검토 파일: country=IDN, change_id, review 객체. --write 없으면 로컬 미리보기
node scripts/indonesia_policy/mail-review.cjs --env-file /ABS/ENV --review /ABS/review.json
node scripts/indonesia_policy/mail-review.cjs --env-file /ABS/ENV --review /ABS/review.json --write
# 수신 대상 집계만 / 운영 게이트가 켜진 뒤 명시적 대기열 생성
node scripts/indonesia_policy/mail-review.cjs --env-file /ABS/ENV --enqueue UUID
node scripts/indonesia_policy/mail-review.cjs --env-file /ABS/ENV --enqueue UUID --write
```

review 필드는 `event_type`(new_document/amended/repealed/effective/official_content_changed), `summary`(20~600자), `reviewer`, `quote`(저장 버전의 정확한 원문), `source_url`, `topics`, `scope`(national/regions), `regions` 배열이다. 예시 검토 자료를 운영 변경 근거로 사용하지 않는다. CLI는 발송 게이트를 켜거나 Resend를 호출하지 않는다.

## 검증 및 인수

메일링 검사 55개(IDN 설치·권한·적용 범위·겹침·재가입·수신 거부·대기열 실패 시 검토 원자 롤백·기존 US 분기 포함), IDN 클라이언트/API 등 13개, 브라우저 6개를 통과했다. 구독 UI 검사는 가짜 Auth/RPC이며 실제 사용자의 구독 저장이나 실제 수신 검증을 대신하지 않는다. 기존 검색·원문·근거 검사는 운영 Supabase를 읽는다. 타입 검사 통과. 유료 AI 호출은 없었다.

Claude 인수 순서:

1. 이 PR을 검토·병합하고 검색 정적 UI와 `services/mailing/core.mjs`가 포함된 메일 Worker를 배포한다. 기존 발송기를 중복 배치하지 않는다.
2. 배포 화면에서 로그인 사용자 본인의 석탄·동칼리만탄 구독 저장·해제를 확인한다. 검토된 실제 신규 변화가 없으면 가짜 규제 이벤트를 만들지 않는다.
3. 공식 목록/원문 수집 주기와 담당을 정한다. 이번 변경은 **저장 시 변화 감지 자동화**이며 수집기 예약을 켠 것이 아니다. 미확보 규정의 발견·적용 범위·효력 검토도 계속 필요하다.
4. 발송기 배포·구독·검토 흐름이 확인된 뒤 service 전용 `idn_set_mail_delivery_enabled(true)`로 IDN 게이트를 켠다. 이 시점 이전 후보는 발송하지 않는다. 기존 전체 MAIL_SEND_ENABLED를 임의로 바꾸지 않는다.
5. 이후 발견하고 검토한 실제 변화의 대기열과 다음 날 아침 공급자 접수·수신을 확인한다. 끌 때는 `idn_set_mail_delivery_enabled(false)`로 IDN만 멈추고 데이터/대기열을 삭제하지 않는다.
