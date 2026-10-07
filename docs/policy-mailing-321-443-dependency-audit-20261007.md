# 메일링 PR #321 · #443 의존성 점검 (2026-10-07)

요청 당시 전제: 운영 Supabase에는 `mailing_outbox`/`mailing_preferences`가 이미 있지만 이를 만드는 PR #321이 main에 없어 새 DB 구축이 불완전한 상태였다.

**조사 중 확인한 사실: 그 전제가 이미 해소돼 있었다.** PR #321(`claude/mailing-production-20260916`)은 이 점검을 시작하기 전인 2026-10-07 01:36 KST에 이미 main에 머지됐다(머지 커밋 `e8ee98d0`). 머지 직전 "PR 321과 main 통합" 작업 자체도 이미 끝나 있었다(`docs/policy-mailing-release-20261007.md`, "10월 4일 처리" 절). 아래는 "머지해도 안전한가"가 아니라 **"이미 병합된 결과가 실제로 안전한가"를 독립적으로 재현·검증**한 결과다. 운영 SQL 실행·PR 병합(이미 끝남)·사이트 배포·실제 발송 전환은 이번 점검에서 하지 않았다.

## 1. #321·#443·운영 DB의 기본 테이블·함수·권한·트리거 차이

운영 DB에 직접 접속할 자격 증명이 이 작업 환경에는 없다. 아래는 (a) 두 PR이 실제로 추가한 migration 파일 원문, (b) #443이 작성한 운영 점검 기록(`docs/policy-mailing-production-audit-20261002.md`)과 #321이 작성한 운영 점검 기록(`docs/policy-mailing-release-20261007.md`)을 근거로 한 비교다.

`mail_capture_bill_stage()` (법안 단계 변경 감지)는 세 세대를 거쳤다 — 모두 `create or replace function`이라 파일명 순서대로 적용하면 마지막 정의가 그대로 남는다:

| 세대 | 파일 | 핵심 로직 |
|---|---|---|
| 1 (약함) | `20260911010000_mailing_outbox.sql` (#321) | `old.current_stage is not distinct from new.current_stage` 비교만. `lifecycle`/표결 내용은 전혀 안 봄. |
| 2 (중간) | `20260920020000_mailing_bill_lifecycle.sql` (#321) | `lifecycle` JSON의 `step_id·stage·latest_event.kind·chamber·date·vote.result` 6개 필드로 식별 키 구성. **같은 날 같은 단계·결과면 표결 종류(cloture vs motion_to_proceed)·찬반 수가 달라도 구분 못함** — #443이 고친 바로 그 결함. |
| 3 (현재) | `20261002010000_mailing_bill_event_identity.sql` (#443) | 2번 키에 정규화된 액션 문구(공백 trim)·`vote.kind`·찬성/반대/present/not_voting 수를 추가. |

`mail_item_active()` (발송 대상 여부 판정)도 두 세대:

| 세대 | 파일 | 정책(policy) 분기 | 원자재(commodity) 분기 |
|---|---|---|---|
| 1 (약함) | `20260911010000_mailing_outbox.sql` (#321) | `mailing_preferences.policy_enabled` + 즐겨찾기 존재만 확인. **계정 일시정지(`bill_notifications_paused`)도, 항목별 알림(`notify_enabled`)도 전혀 안 봄.** | `commodity_enabled` + 수신 기록 없음 + 즐겨찾기+발행일 + 기관 제외만. **`notify_enabled` 역시 안 봄.** |
| 2 (현재) | `20261002020000_mailing_subscription_preferences.sql` (#443) | 위에 `not bill_notifications_paused`와 `f.notify_enabled` 추가. | 위에 `f.notify_enabled` 추가. |

표/트리거/권한은 #321의 `20260911010000_mailing_outbox.sql` 한 파일에서 전부 만들어지고, 이후 어떤 migration도 트리거를 다시 만들지 않는다(`mail_capture_bill_stage()`를 교체할 때만 컬럼 감시 목록을 넓히려고 `drop trigger if exists ... create trigger ...`를 다시 호출— 함수 본문 교체와 별개로 안전함). 권한은 `revoke all ... from anon,authenticated; grant ... to service_role` 패턴이 전 함수에 일관되게 적용돼 있고, `mail_claim/mail_prepare/mail_complete/mail_fail/mail_status`는 `anon`/`authenticated` 둘 다 실행 권한이 없다 — 아래 2번 검증에서 직접 재확인했다.

## 2. #321이 운영의 최신 보호 조건을 덮어썼는가

**아니다.** 세 가지로 확인했다:

1. **파일명 순서가 이미 맞다.** #321의 두 migration(`20260911`, `20260920`)이 #443의 두 migration(`20261002` × 2)보다 파일명이 앞선다. `create or replace function`은 적용된 순서의 마지막 정의가 최종 상태이므로, 폴더 전체를 순서대로 적용하면 항상 #443의 보강판으로 귀결된다.
2. **main의 최종 상태를 직접 읽어 확인했다.** `pg_get_functiondef`로 두 함수의 현재 정의를 뽑아 `yea_count`(법안 식별 키)·`bill_notifications_paused`·`notify_enabled`(발송 대상 판정) 문자열이 들어있는지 확인 — 전부 있음.
3. **#321 자신도 이 위험을 알고 있었다.** PR #321 본문 마지막 줄: "운영 DB에 초기 메일 SQL만 다시 실행하면 최신 함수가 되돌아갈 수 있으므로 이번 수정에서 운영 SQL은 실행하지 않았습니다." — #443의 운영 점검 문서에 있던 동일 경고와 일치한다. 운영 DB에는 이미 #443의 보강판이 직접 적용돼 있고(수동 적용, migration 트래킹 밖), #321은 이번에 운영 SQL을 다시 실행하지 않았으므로 운영 DB의 현재 함수는 이번 머지로 바뀌지 않았다. main 저장소의 migration 역사가 운영 상태를 "따라잡은" 것이다.

**#321 전체를 검토 없이 받아들이지는 않았다** — 실제로 UI 5개 파일(`auth.js`, `mypage.js`, `policy-evidence.js`, `policy.js`, `index.html`)도 같이 바뀌었는데, 이는 별도로 열려 있던 PR #409(즐겨찾기/절차부결 UI 수정, Codex)와 내용이 겹쳤다. 대조해보니 #321 쪽이 이미 해당 변경을 포함한 더 최신 버전이었고, #409는 "추가된 줄의 99%가 이미 main에 있음"을 확인한 뒤 병합 없이 닫혀 있었다(2026-10-07 01:28, #321 머지 8분 전) — 올바른 정리였다.

## 3. 빈 로컬 테스트 DB 재현 검증

기존에 이미 이 정확한 시나리오를 검증하는 테스트가 `services/mailing/test/installation.test.mjs`에 있었다. 직접 git worktree로 현재 main을 체크아웃해 **새로 실행**해서 재확인했다(기존 테스트를 믿지 않고 독립 재현):

```sh
cd services/mailing && npm ci --ignore-scripts && npm test
# → 46 passed
NODE_PATH=<pglite 설치 경로> node --test \
  scripts/lib/policy-mailing-events.test.cjs scripts/lib/policy-mailing-preferences.test.cjs \
  scripts/lib/policy-mailing-archive.test.cjs scripts/lib/policy-mac-resume.test.cjs \
  scripts/lib/policy-mac-lock.test.cjs scripts/lib/commodity-digest-delivery.test.cjs \
  scripts/lib/policy-quality.test.cjs scripts/lib/policy-worker.test.js scripts/lib/policy-evidence.test.js
# → 55 passed
```

빈 PGlite 인스턴스에 앱 필수 테이블(`auth.users`, `profiles`, `user_favorites`, `bills`, `executive_orders`, `commodity_report_notifications`, `commodity_digest_source_prefs`)만 먼저 만들고, 실제 저장소 migration 6개(`20260911010000_mailing_outbox.sql` → `20260919_bill_notification_pause.sql` → `20260919_favorite_notify_enabled.sql` → `20260920020000_mailing_bill_lifecycle.sql` → `20261002010000_mailing_bill_event_identity.sql` → `20261002020000_mailing_subscription_preferences.sql`)를 파일명 순서대로 적용하는 방식 — 요청하신 "기본 구조 → #443 보강" 순서와 동일하다.

요청하신 네 가지 속성 전부 통과 확인:

- **재실행 안전성**: 전체 migration을 한 번 더 적용해도(`create table if not exists`/`create or replace function`) 에러 없고 트리거는 여전히 1개(`pg_trigger` 카운트로 확인). 중복 트리거나 함수 충돌 없음.
- **즐겨찾기 변경 감지**: 같은 날 같은 단계로 두 번(표결 종류만 다르게: cloture → motion_to_proceed) 갱신해도 `mailing_outbox`에 정확히 1건만 쌓임 — #443이 고친 "같은 날 다른 표결 누락" 문제가 실제로 해소돼 있음을 재확인.
- **구독 해제(계정 일시정지)**: `bill_notifications_paused=true`로 바꾸고 `mail_claim()` 호출 → `null` 반환, `mailing_deliveries`에 아무것도 안 쌓임. (항목별 `notify_enabled=false` 구독 해제는 `policy-mailing-preferences.test.cjs`에서 별도로 통과 — `active('policy')`가 즉시 `false`로 바뀜.)
- **중복 알림 방지**: 위 "즐겨찾기 변경 감지" 테스트가 동시에 중복 방지 테스트다. 원자재 쪽은 `commodity_report_notifications`에 수신 기록이 있으면 `mail_item_active()`가 `false`를 반환하는 것을 별도 테스트로 확인.
- (추가 확인) **RPC 격리**: `mail_claim/mail_prepare/mail_complete/mail_fail/mail_status`에 `anon`/`authenticated` 실행 권한이 0건임을 `pg_proc`/`has_function_privilege` 쿼리로 직접 확인.

## 4. 결론 및 후속 작업

**코드 수정 필요 없음.** #321·#443 모두 이미 main에 올라가 있고, 적용 순서(파일명 타임스탬프)가 이미 올바르며, 빈 DB 재현으로 그 결과를 독립적으로 재확인했다. 이번 PR에서 바꾼 것은 문서와 `docs/ops/TASKS.md`의 상태 행 정리뿐이다(두 작업 모두 PR 번호가 이미 붙어 머지됐는데 `review`로 남아 있었음).

**이미 알려진, 이번 점검의 범위 밖인 후속 작업** (새로 발견한 문제 아님 — #321/#443 자신의 문서에 이미 기록돼 있음):

- 실제 발송 전환(`MAIL_SEND_ENABLED=true`)은 기존 `commodity-digest` 발송기 중단 확인 후 별도 승인 필요.
- 맥 법안/RSS 수집기의 다음 예약 실행 확인(진행 중, 이번 점검과 무관).
- 실제 로그인 브라우저에서 별 클릭 → 마이페이지 표시 확인은 사이트 로그인 상태가 필요해 보류 중.

검증: 새로 실행한 테스트 101개(서비스 46 + lib 55) 전부 통과. 운영 SQL 실행·사이트 배포·실제 메일 발송 없음.
