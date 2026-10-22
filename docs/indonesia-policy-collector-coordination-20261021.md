# 인도네시아 수집 실행·메일 근거 통제 (2026-10-21)

## 적용 범위와 현재 상태

검토된 공식 출처의 제한된 재수집에 호스트 간 잠금, 실패 상태, 운영 조회를 추가했다. 실제 재수집에서 발견한 메타데이터 변화가 규제 개정 메일로 승격되지 않도록 원문 조건도 강화했다. 미국 수집·메일, 사이트 배포, 반복 예약은 변경하지 않았다. 유료 AI 호출과 실제 메일 발송은 0회다.

운영 DB는 **문서 73건 / 버전 83건 / IDN 구독 0건 / 발송 대기 0건**이다. 원문 미확보 변화 2건은 `held`이며 `delivery_enabled=false`다. 법령의 현재 효력은 별도 근거 검토 대상이고, 이번 수집 확인으로 유효 법령이라고 확정하지 않는다.

## 여러 실행기의 충돌 방지

`sync_reviewed.py --write`는 먼저 서비스 전용 DB lease를 얻는다. 모든 IDN 단계가 같은 잠금을 공유한다. 다른 Mac/GitHub 실행기가 사용 중이면 공식 사이트에 요청하지 않고 종료한다. 기존 상태 폴더의 파일 잠금도 유지한다.

- 유효기간은 15분이며 항목 시작과 저장 전마다 갱신한다. 강제 종료된 실행기의 잠금은 만료로 회복한다. 수동 강제 해제 기능은 제공하지 않는다.
- 원문·출처 확인 저장 RPC는 같은 트랜잭션에서 토큰·만료를 검사하고 lease 행을 잠근다. 이전 실행기가 멈췄다가 돌아와도 만료/교체된 토큰으로 저장하거나 새 실행기의 잠금을 해제할 수 없다.
- DB/네트워크 오류는 원본 파일과 커서를 보존한다. 출처 확인 RPC의 응답도 boolean인지 검증하고, 확인되지 않은 응답으로 커서를 넘기지 않는다.
- 토큰은 상태 파일·로그·상태 조회에 출력하지 않는다. 일반 사용자는 테이블과 운영 RPC에 접근할 수 없다.

이 잠금은 새 실행기의 경로에 적용된다. 이전 `collect.py`/`import.cjs` 등 관리자 수동 경로까지 잠금으로 감쌌다고 주장하지 않는다. 배포 후 정기 수집은 새 실행기 하나로 통일한다. 긴 시스템 정지로 lease가 만료되면 기존 HTTP 요청이 잠깐 남을 수 있으나 후속 DB 저장은 거부한다. 다른 호스트로 전환해도 체크포인트·호스트 차단 이력을 별도로 보존해야 한다.

## 실행 결과 해석

| state | 의미 | 종료 코드 |
| --- | --- | --- |
| `ok` | 이번 배치에서 시도한 원문을 모두 완전한 본문으로 확인 | 0 |
| `partial` | 완전 원문 일부 확인, 실패·메타데이터·차단 대기 포함 | 0 |
| `unavailable` | 시도했으나 완전 원문 확인 0건 | 2 |
| `deferred` | 호스트 대기 등으로 이번 배치의 시도 0건 | 2 |
| `stopped` | STOP 파일을 확인하고 작업 경계에서 중단 | 0 |

`status.json.last_batch`에 결과를 남긴다. `ok`도 해당 배치의 관측 결과이며 전국 전수 수집·현재 법적 효력·전체 PDF 첨부 확보를 의미하지 않는다. 부분 실패는 다음 실행에서 커서를 이어가며 다른 출처까지 막지 않는다.

```bash
cd /Users/yeoninair/Documents/policy-indonesia-20261017

# 상태 조회만: 원문 다운로드, DB 쓰기 없음
/Users/yeoninair/Documents/policy-runtimes/idn-sync/bin/python scripts/indonesia_policy/sync_reviewed.py \
  --status --env-file /Users/yeoninair/Documents/global-trade-dashboard-local/.env.local

# 보류 후보와 사유 조회: 발송하지 않음
node scripts/indonesia_policy/mail-review.cjs \
  --env-file /Users/yeoninair/Documents/global-trade-dashboard-local/.env.local
```

`--status`는 잠금 사용 여부·문서/버전 수·최근 출처 확인 시각·24시간 결과 집계·검토 대기·발송 게이트를 반환한다. `collected`에는 메타데이터 확인도 포함되므로 완전 원문 수와 혼동하지 않는다. 상태 폴더의 배치 결과에 있는 `complete_text_checks`와 함께 본다. 검토 CLI는 `--hold CHANGE_ID`로 계획을 확인하고 `--write`를 붙여 보류할 수 있다. 보류는 미발송 항목을 억제하며 이미 공급자에 접수된 메일을 회수하지 않는다.

## 메타데이터 변화는 자동 보류

공식 사이트의 제목·링크·메뉴 변화, PDF 다운로드 실패, 잘린 본문은 버전/실패 근거로 보존하지만 메일 검토 가능한 완전 원문과 구분한다.

`policy_idn.mail_changes`의 INSERT/UPDATE 트리거가 해당 버전의 `content_kind=official_text AND text_truncated=false`를 검사한다. 불완전한 버전은 즉시 `held`, `hold_reason=incomplete_official_text`, `held_at`을 기록한다. `pending`으로 돌리려 해도 보류되며 `reviewed` 승격은 오류로 거부한다. 이미 저장된 불완전 후보도 제한된 UPDATE로 보류했다. 문서·버전·원문 이력은 삭제하지 않았다.

이후 완전한 원문을 확보하면 별도 버전의 후보가 생긴다. 그 후보도 원문 인용·공식 URL·상품·지역·실제 개정 여부를 검토해야 한다. 원문 복구나 해시 변화만으로 법령 개정이라고 판단하지 않는다. 기존 보류 버전은 자동 해제하지 않는다.

## 실제 재수집과 검증

석탄 레지스트리 앞 10개를 제한된 배치로 실행했다. 원문 6건, 메타데이터 2건, 원본 페이지 접속 실패 1건, 호스트 차단 대기 1건이었다. 메타데이터 중 1건은 PDF 크기 제한으로 본문을 받지 못했다. 실행 결과는 `partial`이며 9건 시도·2건 실패 기록(페이지 1 + PDF 본문 1)·원문 확인 6건·커서 10을 남겼다. 새 법령을 추가한 것이 아니라 기존 메타데이터 버전 2건을 갱신했다.

보류한 항목:

- `idn-kaltim-perda-7-2025`: 동칼리만탄 환경 보호·관리 규정의 목록 메타데이터 변화. PDF 크기 제한, 완전 본문 미확보.
- `idn-kaltim-pergub-23-2024`: 사업 환경관리 등급 평가 관련 주지사 규정의 목록 메타데이터 변화. 검토된 입력 자체가 metadata-only.

Python 47개, 메일링 60개(가짜 Resend·SQL 설치 포함) 검사와 타입 검사를 통과했다. 실제 Supabase에서도 두 실행기의 잠금 경합·갱신·해제, 두 후보의 보류, 발송 대기 0건을 확인했다. 기존 사용자 로그인 구독/실제 수신을 대신하는 검증은 아니다.

## Migration·백업·인수

- `20261020231311_indonesia_sync_lease.sql`
- `20261020231617_indonesia_mail_complete_source_gate.sql`

두 migration을 운영에 적용했고 파일/운영 이력 SQL MD5가 각각 `5bb4ccf2d3005e79a6ef9f82dfe107f4`, `bfc8a5b1977258f82d7bb43b079eeeda`로 일치한다. CLI로 생성한 lease 파일은 플러그인이 실제 부여한 운영 버전에 맞춰 이름을 정렬했다. 두 번째 적용의 플러그인 요청 만료는 미반영을 조회한 뒤 SQL 경로로 처리했다. 이번 신규 이력 1행의 전달 과정에서 생긴 달러 구분자 오류도 원문 해시 일치 조건으로 교정했다. 이전 migration 이력은 수정하지 않았다.

적용 전 스냅샷은 저장소 밖 비공개 `policy-downloads/indonesia-20261021/mailing/pre-sync-lease.json`, `pre-mail-complete-source.json`이다. 수집 체크포인트는 `policy-downloads/indonesia-sync/coal/`에 있다. 시크릿·사용자 주소는 PR에 넣지 않는다. Security Advisors의 private 서비스 테이블 RLS 기본 거부 INFO는 의도한 접근 제한이다.

Claude 인수 시 PR #652를 검토하고 UI/메일 Worker를 배포한다. 실제 계정의 상품·지역 구독/해제, 새 원문 변화 검토, 대기열과 최종 수신 거부를 확인한 뒤 IDN 게이트를 별도로 켠다. 기존 메일 sender를 중복 배치하지 않는다.

정기 수집은 아직 설정하지 않았다. 103개 출처를 한 번에 최대 20개씩 확인하면 한 순회에 6배치가 필요하다. 모든 단계를 4시간 간격으로 돌리면 대략 하루, 하루 한 번이면 약 6일이며 차단·실패는 별도다. GitHub 전환 시 단일 concurrency 그룹과 체크포인트 artifact의 복원/저장이 필요하다. 이번 턴에서는 주기를 임의 활성화하거나 미국 workflow를 수정하지 않았다.
