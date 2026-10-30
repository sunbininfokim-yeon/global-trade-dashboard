# 법안 변경 메일 운영 점검 · 2026-10-02

운영 Supabase에서 메일 함수 10개와 관련 트리거를 직접 조회했습니다. 발송 Worker는 `chokemonitor-mailing`, 발신 주소는 `alerts@chokemonitor.com`입니다. 현재 `MAIL_SEND_ENABLED=false`이므로 자동 발송은 활성화되지 않았습니다.

## 이번 운영 적용

`20261002010000_mailing_bill_event_identity.sql`의 `mail_capture_bill_stage()`를 적용했습니다. 같은 날 같은 단계·결과인 표결도 액션 문구, 표결 종류와 찬반 수가 다르면 감지합니다. 반복 수집, 공백 변경, 화면 라벨·출처 URL·DB 행 ID 변경은 새 메일 이벤트를 만들지 않습니다. 최초 lifecycle 스냅샷은 기준점만 설정합니다.

정확한 원문·체크섬을 비공개 로컬 백업하고, 백업 이후 함수가 달라지면 중단하는 조건을 추가한 짧은 트랜잭션으로 교체했습니다. 기존 트리거·즐겨찾기·발송 대기열은 수정하지 않았습니다. 운영 검증 결과 감지 보강=true, 법안 변경 트리거=1, 새 발송 대기열=0입니다. 실제 법안 상태를 테스트용으로 변경하지 않았습니다.

운영 SQL 편집기:

- [조회 · 메일링 함수·트리거 정의 확인](https://supabase.com/dashboard/project/sjkjjobeahibxgbtomcu/sql/ea580d66-9116-46ea-a2e5-af570f844184): 읽기 전용.
- [적용완료 · 같은 날 표결 변화 메일 감지 보강](https://supabase.com/dashboard/project/sjkjjobeahibxgbtomcu/sql/9185da8c-d61a-4223-9035-55538e47722d): 이미 적용됨. 저장된 운영 실행문은 이전 함수 체크섬으로 보호돼 재실행 시 중단됩니다. 저장소 migration 자체는 재실행 가능합니다.

## 운영 DB와 PR #321 차이

메일 함수 9개의 본문은 PR #321의 SQL과 의미상 일치했습니다. `mail_item_active()`는 운영 DB에 더 최신 조건이 있었습니다. 계정의 `bill_notifications_paused` 및 즐겨찾기의 `notify_enabled`를 확인합니다. 이를 `20261002020000_mailing_subscription_preferences.sql`로 기록하고 두 개의 PostgreSQL 회귀 테스트를 추가했습니다. 운영 함수는 이미 이 내용이므로 이번에 다시 교체하지 않았습니다.

PR #321의 초기 outbox migration을 운영에 그대로 재실행하면 이 보호 조건이나 이후 lifecycle 감지 보강이 옛 버전으로 돌아갈 수 있습니다. 초기 메일 테이블 설치 뒤 이 날짜의 두 migration을 순서대로 적용해야 합니다. 이번 변경은 PR #321 전체를 병합하거나 새 DB의 메일 기본 테이블을 설치하지 않습니다. PR #321의 서비스·스키마·워크플로 통합은 별도 확인이 필요합니다. RSS 아카이브 스크립트는 이번 변경에서 독립적으로 복구했습니다.

## 수집과 발송의 경계

맥 수집기는 4시간 간격으로 실행됩니다. 2026-10-02 두 번째 실행에서 즐겨찾기 법안 4개를 먼저 확인하고 일반 법안 100건 처리를 완료했습니다. 해당 실행의 임베딩 재계산은 0건입니다. 이미 저장된 벡터와 수집 대기열의 건수는 서로 다른 지표입니다.

법안 변경 메일의 `due_at`은 DB에서 변화를 감지한 다음 한국 날짜의 06:00입니다. 공식 액션 날짜와 DB 감지 시각은 별도로 저장합니다. 맥의 전원·인터넷이 끊기면 감지가 지연됩니다. 발송 Worker는 10분마다 확인하며, 실제 발송 활성화와 수신함 도착 검증은 이번 DB 함수 적용에 포함되지 않았습니다.

기존 `commodity-digest.yml` 예약은 활성 상태입니다. 이 발송기는 새 Worker와 분리되어 있으므로, 전체 메일 전환 전 기존 발송을 중단하고 실행 중인 작업이 없음을 확인해야 합니다. Congress GitHub 수집은 `disabled_manually`이며 맥과 중복 실행하지 않습니다.

## RSS 보관 복구와 맥 운영 연결

운영 `mailing_reports`를 39건에서 98건으로 복구했습니다. GitHub main에서 읽은 스냅샷의 유효 보고서 63건과 더 최신으로 생성된 보존 스냅샷의 유효 보고서 65건을 `report_id` 충돌 키로 저장했습니다. 같은 항목은 중복 행이 생기지 않습니다. 복구 후 최근 발행 시각은 2026-10-01 23:15 KST이며, 원자재 대기 항목 3건의 예약은 2026-10-05 월요일 08:00 KST입니다. 실제 메일은 발송하지 않았습니다.

main 스냅샷은 117개 중 54개를 제외했습니다. 발행일 불명 38개, 원자재 분류 없음 39개이며 23개가 겹칩니다. 보존 스냅샷은 82개 중 발행일 불명 17개를 제외했습니다. 날짜를 임의 생성하거나 정책 공고에 원자재 태그를 강제로 붙이지 않습니다. 잘못된 URL·손상된 날짜·필수 필드 누락은 건너뛰기 옵션으로 허용하지 않습니다. 보고서 제목·요약·주제·공식 링크를 저장하며 PDF 파일 자체를 DB에 저장하는 작업은 아닙니다.

맥 체크아웃의 실행기를 커밋 `80936f3e`로 교체했습니다. 정상 대기 경계에서 이전 프로세스가 종료된 뒤 새 실행기 한 개(PID 33401)가 대기하는 것을 확인했고, 기존 다음 실행 시각 2026-10-02 16:50:12 KST를 유지했습니다. 이후 Congress 수집이 성공하면 RSS 아카이브를 실행합니다. 아카이브 실패는 `archive_exit_code`와 `partial_archive_failed`로 기록합니다. 이 첫 예약 실행의 RSS 훅 결과는 아직 확인 전입니다.

이 맥 작업은 GitHub에 생성된 RSS 결과 JSON을 읽어 DB에 보관합니다. EIA·USDA 원본 피드를 직접 수집·분류하는 실행기를 맥으로 옮긴 것은 아닙니다. main/배포 스냅샷의 생성 시각은 2026-10-01 19:27 KST, 더 최신 보존본은 2026-10-02 06:20 KST로 달라 upstream 발행·배포 최신성은 별도로 확인해야 합니다. GitHub API 조회 자체는 Actions 실행 시간을 사용하지 않습니다.

- [조회 · 메일 대기열·RSS 보관·감지 상태](https://supabase.com/dashboard/project/sjkjjobeahibxgbtomcu/sql/ea18a2d5-2fe2-4ea1-8c47-0ab55a543c0a): 저장된 읽기 전용 운영 점검.
- 비공개 백업: `/Users/yeoninair/Documents/policy-downloads/backups/mail-20261002/`의 정확한 함수 원문·체크섬과 롤백 SQL. 저장소에는 포함하지 않습니다.

## 검증

새 테스트 15개(SQL 7개, RSS 5개, 재시작 일정 3개)가 통과했습니다. 기준점·반복 처리, 같은 날 서로 다른 표결, 찬반 수 보정, 표시 문구 변경, 트랜잭션 롤백, 계정 일시정지·항목별 알림·채널별 알림·기관별 수신 설정·기존 발송 기록·구독 시작 시점 조건을 검증했습니다. 앞서 PR #321의 메일 서비스 테스트 44개도 통과했지만 실제 발송 성공을 뜻하지는 않습니다.

테스트 의존성은 `@electric-sql/pglite@0.5.8`입니다. 저장소에 별도 공통 npm 설치가 없으므로 격리된 위치에 설치해 실행할 수 있습니다.

```sh
npm install --prefix /private/tmp/policy-mail-test-runtime --ignore-scripts --no-package-lock --no-save @electric-sql/pglite@0.5.8
NODE_PATH=/private/tmp/policy-mail-test-runtime/node_modules node --test scripts/lib/policy-mailing-events.test.cjs scripts/lib/policy-mailing-preferences.test.cjs scripts/lib/policy-mailing-archive.test.cjs scripts/lib/policy-mac-resume.test.cjs
```
