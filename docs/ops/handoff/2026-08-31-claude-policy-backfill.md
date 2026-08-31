# 인수인계 2026-08-31 — claude (미국 정책 데이터 적재)

## 2026-08-31 — claude

### Goal / summary

미국 정책 데이터(법안·행정명령·규제)를 Supabase에 적재한다. 초기 백필은 한 번
크게 담고, 이후에는 하루 1회 또는 3일 1회 증분으로 유지하는 것이 목표다.

이 인수인계는 **적재 운영 전용**이다. UI(`New for anti/**`)는 다른 세션이
소유하며 여기서 건드리지 않는다.

### Meta

- branch: `claude/postgresql-requirements-85a9j6` (UI 세션이 쓰는 브랜치. 적재
  작업은 코드 변경이 거의 없으므로 보통 `main` 기준으로 읽기만 하면 된다)
- head: `51d6f3a` / `origin/main`: `c95582b`
- 워크플로우: `.github/workflows/sync-congress.yml` — "Sync US Government Policy Data"
- 계약서: `docs/api-spec.md` (코덱스 작성, 정본), 화면 매핑 `docs/ui-screens.md`

### 지금까지 일어난 일

- 2026-08-29~30: 파이프라인 최초 투입. 실행 #1~#11 중 대부분 실패.
- 실패 원인은 두 가지였고 **둘 다 PR #203에서 고쳐져 머지됨**:
  1. Gemini 임베딩이 1536차원을 기대하는데 3072차원을 반환. 요청 본문에서
     `taskType`/`outputDimensionality`를 `embedContentConfig` 래퍼 안에 넣었는데,
     `batchEmbedContents` REST 스키마엔 그런 필드가 없어 서버가 무시하고
     기본 차원으로 응답했다. flat 필드로 옮겨 해결.
  2. `bill_summaries` 중복 확인을 `summary_text=eq.<요약 전문>` GET 쿼리로 해서
     요약이 긴 법안(119-hr-1)에서 `HTTP 414`. `bill_id`+`action_date`+
     `version_code`로 조회 후 텍스트를 로컬 비교하도록 변경.
- **run #12 (33350584709, 2026-08-31 02:24Z)가 첫 성공.**
- PR #204 머지: `agencies.agency_type`(`eop|department|independent|sub`)과
  Federal Register `parent_id` → 로컬 `parent_agency_id` 해석 추가.

### 측정된 수치 (다시 재지 말 것)

run #12 로그 기준. 그 실행은 `MAX_BILLS=25`, `MAX_PUBLIC_LAWS=10`,
`MAX_FR_DOCUMENTS=10`으로 수동 실행된 것이다.

| 단계 | 소요 |
|---|---|
| Congress.gov bills | 7분 11초 (탐색 ~2.5분 + 법안 25건 ~4.7분) |
| Federal Register | 31초 |
| U.S. Code | 7초 |
| Public Law | 3분 46초 |
| **전체** | **12분** |

- **법안 1건당 약 11초.** 법안마다 상세·요약·액션·위원회·주제·본문링크·
  관련법안·표결을 각각 호출한다. `CONGRESS_REQUEST_INTERVAL_MS=850`이
  Congress.gov 시간당 5,000회 제한(≈0.72초/회)에 이미 붙어 있어 더 못 줄인다.
- 기본값(`MAX_BILLS=100`)으로 돈 정기 실행 #10은 **22분**.
- 따라서 **법안 N건 백필 ≈ N × 11초.**

### 백필 규모 판단

119대 의회 전체를 1.5만 건으로 가정하면 **약 46시간**이다. 직전 118대가 약
1.8만 건이었다는 통념에 기댄 추정이므로, **정확한 수는 bootstrap 탐색 1회를
돌려 로그의 `discovered` 값으로 확정할 것.** 추정으로 진행하지 말 것.

46시간은 GitHub Actions Free 월 2,000분(33시간)을 넘긴다. Pro(3,000분=50시간)
여도 그 달에 다른 워크플로우 20여 개를 거의 못 돌린다. 실행을 며칠로 쪼개도
총량은 같다.

**선택지 (아직 미결. 사용자와 정하고 시작할 것):**

1. **로컬 실행 (권장)** — 스크립트가 평범한 Node라 사용자 PC에서 동일하게 돈다.
   Actions 분을 0분 쓴다. Congress.gov 속도 제한은 API 키 기준이라 46시간은
   그대로지만, 그 시간이 무료 한도를 안 깎는다. 맥이 켜져 있어야 하고
   잠자기 방지가 필요하다.
2. **범위 축소** — 1.5만 건 대부분은 발의만 되고 끝난 법안이다.
   `reported`(상임위 통과) 이상만 담으면 1~2천 건, 4~6시간이라 Actions로
   감당된다. UI가 실제로 보여주는 것도 대부분 이 범위다.
3. **Actions로 전량** — 무료 한도를 넘긴다. 플랜 확인이 먼저다.

1+2 조합(로컬로 전량 담되 `reported` 이상부터 우선)이 현재 추천안.

### 이 세션이 할 수 없는 것

- **Supabase에 직접 접속 불가.** `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`는
  GitHub Actions secret이라 세션 환경에 없다. SQL 실행·테이블 조회·DB 크기
  확인은 전부 사용자에게 요청해야 한다. **추측으로 "적재됐다"고 보고하지 말 것.**
- 마이그레이션 SQL을 대신 실행할 수 없다.
- GitHub Actions 계정 플랜(Free/Pro)을 조회할 수 없다. `billable`이 0으로
  반환된다. 남은 분은 사용자가 Settings → Billing에서 확인해야 한다.

### Not done / risks

- **`supabase/migrations/20260831_policy_agency_types.sql` 실행 여부 미확인.**
  PR #204의 배포 순서상 SQL Editor에서 먼저 돌려야 한다. **이게 안 된 상태로
  백필하면 `agency_type`이 비어 UI의 기관 블록이 어긋난다.** 가장 먼저 확인할 것.
- **Supabase Free 500MB가 가장 강한 제약이다.** 넘으면 프로젝트가 읽기 전용이
  될 수 있다. `docs/api-spec.md`의 "Supabase Free Plan 안전 기본값" 절을 읽고
  따를 것: bootstrap은 `MAX_BILLS=25`부터, 배치마다 사용자에게
  Supabase Dashboard → Settings → Usage의 DB 크기를 물어보고,
  **400MB에 근접하면 멈추고 보고.** 스스로 계속 진행하지 말 것.
- 백필 중 정기 실행(하루 1회 `17 2 * * *`)이 겹치면 같은 큐를 두 곳에서 건드린다.
  로컬 백필을 돌리는 동안은 스케줄을 잠시 끄는 것이 안전하다.
  `.github/workflows/**`는 claude 소유이므로 UI 세션에 요청하면 된다.
- Actions로 돌릴 경우 **하루 2~3회를 넘기지 말 것.** 이 레포엔 다른 스케줄
  워크플로우가 20개 넘게 같은 한도를 나눠 쓴다. 참고로 시간당 크론인
  `commodity_news_ticker`는 실제로는 하루 7회 정도만 실행된다 — GitHub이
  비공개 저장소의 잦은 스케줄을 드롭한다.

### 소유권 경계

- `scripts/sync-*.js`, `scripts/lib/**` — **코덱스 영역.** 버그를 찾으면 직접
  고치지 말고 원인과 재현 근거를 정리해 사용자에게 보고할 것.
- `New for anti/**` — UI 세션(Opus) 영역. 건드리지 말 것.
- `.github/workflows/**`, `docs/ops/**`, `tools/ops/**` — claude 소유.
- `docs/api-spec.md`, `docs/ui-screens.md`, `schema.sql`, `supabase/migrations/**`
  — 코덱스 작성. 읽고 따르되 임의로 고치지 말 것.

### Next

1. 마이그레이션 `20260831_policy_agency_types.sql` 적용 여부를 사용자에게 확인.
   안 됐으면 실행 요청하고, 그 전까지 백필하지 않는다.
2. bootstrap 탐색 1회로 119대 실제 법안 수를 확정한다.
3. 그 수를 근거로 위 3안 중 하나를 사용자와 정한다.
4. 정해진 방식으로 배치를 돌리되, 배치마다 DB 크기를 확인받는다.

### 보고 규칙

- **API 키, Supabase 인증정보, 임베딩 벡터 원문을 로그·보고 어디에도 출력하지 말 것.**
- 매 실행 후: 소스별 적재 건수 / 임베딩 건수와 차원 / 소요 시간 / 실행 링크.
- 실패는 로그에서 원인을 특정해 보고한다. "flake"로 넘기지 말 것.

### Commands

```bash
./tools/ops/status.sh

# 최근 실행 확인 (GitHub MCP 도구 사용)
#   mcp__github__actions_list  method=list_workflow_runs  resource_id=sync-congress.yml
#   mcp__github__actions_get   method=get_workflow_run    resource_id=<run_id>
#   mcp__github__get_job_logs  job_id=<job_id>  return_content=true

# 로컬 실행 (선택지 1을 택한 경우 — 키 값은 사용자가 직접 넣는다)
export CONGRESS_API_KEY='...' DATA_GOV_API_KEY='...'
export SUPABASE_URL='...' SUPABASE_SERVICE_ROLE_KEY='...' GEMINI_API_KEY='...'
export SYNC_MODE=bootstrap MAX_BILLS=200
node scripts/sync-congress.js
```

---
