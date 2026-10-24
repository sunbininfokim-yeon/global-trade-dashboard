# 2026-10-24 — 메일 보관 사고 검증 및 후속 방어

사용자 요청: main의 `2026-10-22-claude-to-codex-mailing-archive.md` 인수.
검토 기준 main: `9cbbf289`. PR #665는 2026-10-22 14:15:45 UTC 병합됨.
이번 작업은 운영 DB 읽기 조회와 로컬 코드·테스트만 수행했다. DB 수정, 실제 메일
발송, workflow 실행·활성화, 병합·배포는 하지 않았다.

## 1. 긴급 조치는 설계에 맞음 — 추가 삭제 불필요

운영 조회로 당시 suppression 시각(2026-10-22 04:07:01.330972 UTC)의 33개 소스
사고 대기열을 다시 확인했다. 회원 식별자·이메일·원본 대기열은 공개하지 않는다.

| 검증 대상 | 현재 확인 건수 |
|---|---:|
| 사고 대기열, suppressed 상태 | 47 |
| delivery에 선점된 사고 건 | 0 |
| 사고 건의 sent delivery | 0 |
| 해당 report_id의 edition receipts / legacy notifications | 0 / 0 |
| 해당 report_id의 검색용 reports / legacy notifications_queued | 0 / 0 |
| 해당 ID가 포함된 data_sync_runs.metadata / data_sync_state.cursor | 0 / 0 |

- `mailing_report_editions.report_id`는 보고서 DELETE 시 CASCADE된다.
- `mailing_outbox`는 보고서 FK가 없으므로 차단된 47건이 감사·중복 방지 기록으로
  남는다. 이를 지우거나 가짜 발송 receipt로 바꿀 필요가 없다.
- 보고서 capture trigger는 INSERT/UPDATE에만 걸린다. DELETE로 새 알림이 생기지 않는다.
- `mail_claim`은 suppressed 행을 선점하지 않는다. receipt trigger는 delivery의
  실제 sent 전환에만 동작한다. 운영 함수 본문과 FK/trigger 카탈로그를 확인했다.
- 재수집이 기존 suppressed 사건을 되살리지 않는다. 로컬 PGlite에서 suppression →
  보고서 DELETE → 동일 판 재수집 → 다음 판 수집 순서까지 회귀검사했다.

**현재 같은 33개 source_id를 일괄 삭제하면 안 된다.** 현재 `id_gapki_en` 5건,
`my_mpoc_news` 8건이 있으며 첫 재보관은 병합 후인 10/22 14:23 UTC다. 사고에서
차단된 ID와 겹치는 보고서·edition도 각 10건 재보관되어 있다. 이는 긴급 삭제가
실패했다는 증거가 아니다. 추가로 보이는 미차단 후보 1건도 병합 후 MPOC 수집으로
생겼으므로 이번 사고 대상으로 차단하지 않았다.

검증 한계: 사고 당시 381개 전체 ID 원본 백업을 재확보한 것은 아니다. 381건 삭제와
직후 0건은 Claude의 인계 기록이며, 이번 독립 확인은 복원 가능한 47개 사건의 ID,
33개 소스의 현재 보관 상태, FK와 실행 함수 및 관련 통계·큐 경로를 대상으로 한다.
모든 외부 로그에서 381개 ID가 사라졌다는 주장은 하지 않는다. 감사 기록은 보존한다.

## 2. #665 방어책 검토와 이번 보강

기존 `commodity_reports.yml`의 archive 단계 main 조건과 단계별 secret 범위는
이번 사고의 직접 경로를 막는다. `continue-on-error`와 실패 시 snapshot artifact도
유지한다. workflow 전체 성공만으로 DB 보관 성공을 판단하면 안 된다.

이번 코드 변경:

1. snapshot의 `publisher_type`뿐 아니라 **커밋된 source catalog의 뉴스 지정**도
   확인한다. 옛 snapshot에 표시가 없거나 잘못된 `official` 표시가 있어도 지정 뉴스는
   제외한다. 타입 문자열의 대소문자·공백도 정규화한다.
2. 기본 DB adapter를 사용하는 archive 함수와 CLI가 Actions 실행 문맥을 재검증한다.
   해당 저장소의 `refs/heads/main` + schedule/workflow_dispatch만 쓰기를 허용한다.
   브랜치·태그·PR·누락 문맥은 snapshot 읽기와 DB adapter 로딩 전에 실패한다.
   로컬 Mac 복구와 dry-run은 유지한다. 테스트의 명시적 mock adapter는 DB에 접속하지 않는다.
3. 삭제 후 같은 판 재수집이 suppression을 해제하거나 receipt를 만들지 않고,
   다음 판은 새 알림 후보가 되는지 검사한다.

뉴스 정책은 #665의 방향을 유지한다. 카탈로그에서 뉴스 발행사로 지정된 항목을
개별 보고서 메일에서 제외한다. 기관·협회가 발표하는 시장 기사까지 본문 의미로
판별하는 정책은 아니다. 예를 들어 MPOC는 현재 기관 소스로 분류되므로 유지한다.
구형 digest의 뉴스 상품별 상한 2건을 현재 Worker가 적용한다고 설명하면 안 된다.
뉴스가 사이트에 표시되는 것과 메일 보관 제외는 별개다.

## 3. 다른 브랜치 → 운영 DB 경로 감사

아래는 현재 main 코드 및 10/24 공개 GitHub API의 workflow 활성 상태를 대조한 결과다.
이번 요청에서 다른 workflow는 점검·인계 대상으로 두었고 수정·실행하지 않았다.

| workflow | 현재 상태 | 브랜치 수동 실행의 운영 접근 |
|---|---|---|
| `commodity_reports.yml` | active | 기존 archive main 조건 있음. 이번 PR에서 script 자체도 방어 |
| `sync-congress.yml` | active | job의 운영 키와 브랜치 checkout으로 법안·법률·EO·regulation 등에 쓰기 가능 |
| `sync-indonesia-policy.yml` | active | collector SHA는 고정이지만 호출하는 `tools/idn_sync/run_cloud.py`는 브랜치 코드이며 운영 키 사용 |
| `rollover-congress.yml` | active | 기본 dry-run도 운영 조회. 수동 `allow_purge=true`이면 이전 회기 삭제 가능 |
| `sync-policy-reference-monthly.yml` | disabled_manually | 재활성화하면 브랜치에서 위원회·의원 참조정보 쓰기 경로 있음 |
| `commodity-digest.yml` | disabled_manually | 재활성화하고 dry_run=false로 실행하면 구형 DB 쓰기·Resend 발송 경로 있음. 재활성화 금지 |
| `deploy-mailing.yml` | active | job main 조건 있음 |
| `mailing-checks.yml` | 테스트 전용 | 운영 DB secret 없음 |

`sync-congress.yml`의 구형 법안 메일 단계는 별도 repository variable 조건이 있다.
이번 감사에서 그 variable 값이나 실제 발송 활성 상태를 새로 확인한 것은 아니다.
Mac 수집기는 의도적으로 운영 DB를 사용하며 이번 변경은 실행 중인 수집기를 조작하지 않는다.

Claude/사용자 후속 변경안:

1. 활성 3개 workflow의 운영 job에 `if: github.ref == 'refs/heads/main'`을 넣는다.
   비활성 reference/digest에도 재활성화 전에 같은 제한이 필요하다. rollover의
   dry-run 기본값과 명시 purge 승인은 유지한다.
2. main 조건은 실수 방지다. 브랜치 코드를 바꿀 권한이 있는 실행자가 조건 자체를
   삭제하는 상황까지 막으려면 production GitHub Environment의 main-only deployment
   branch policy를 설정하고 운영 키를 그 environment로 옮겨야 한다. repository에
   같은 운영 키가 계속 남아 있으면 environment 설정만으로 접근을 제한할 수 없다.
3. staging/preview는 별도 DB와 별도 키를 사용한다. 브랜치 수집은 preview만 실행하며
   운영 메일 후보를 만들지 않는지 확인한다. repository 설정 변경은 별도 승인·검증한다.

## 검증

- `node --test scripts/lib/policy-mailing-archive.test.cjs services/mailing/test/*.test.mjs`:
  93/93 통과. 실제 Supabase/Resend/Gemini 호출 없이 수행.
- 추가 메일링/수집 재개·잠금/검색·즐겨찾기 회귀검사 62/62 통과.
- 소유권 규칙 검사 15/15 및 git diff 검사 통과. workflow/UI/SQL 파일 변경 없음.
- 운영 DB는 읽기만 검증했다. 이번 코드가 운영 수집에 적용되려면 사용자 확정 후
  PR 병합이 필요하다. Worker 코드·SQL 변경은 없으므로 Worker 재배포나 migration은 없다.
