# 로컬에서 정책 동기화 스크립트 실행하기

`node scripts/sync-policy-reference-data.js` 같은 `scripts/*.js`를 로컬에서 돌릴 때
필요한 키 3개를 매번 터미널에 `export`로 넣을 필요 없습니다. 한 번만 파일로 저장해두면
그 뒤로는 다른 준비 없이 실행만 하면 됩니다.

## 처음 한 번만

1. `.env.example`을 복사해서 `.env.local`로 저장 (`cp .env.example .env.local`)
2. `.env.local`을 텍스트 에디터로 열고, `=` 뒤에 값만 붙여넣기 — `export ...` 명령문이나
   터미널에 치는 줄 전체가 아니라 **키 값 자체만** 넣습니다.
3. 저장. `.env.local`은 `.gitignore`에 있어서 커밋되거나 Git에 올라가지 않습니다.

## 어디서 값을 복사하나

| 키 | 위치 |
|---|---|
| `SUPABASE_URL` | Supabase 대시보드 → 이 프로젝트 → Project Settings → API → Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | 같은 화면 → Project API keys → **service_role** (anon 키 아님) |
| `CONGRESS_API_KEY` | https://api.congress.gov/sign-up/ 에서 신청하면 이메일로 옴 |

## 실행

```bash
node scripts/sync-policy-reference-data.js
```

터미널을 새로 열어도, 재부팅해도 다시 설정할 필요 없습니다 — `.env.local` 파일이
남아있는 한 스크립트가 알아서 읽습니다. 실제 `export`로 환경변수를 설정해둔 값이
있으면 그게 항상 우선합니다(CI/배포 환경은 원래 이 파일 없이 그대로 동작).

## 안전 수칙

- `.env.local`은 절대 커밋·붙여넣기·채팅에 공유하지 않습니다.
- 스크립트 로그에는 키 이름이나 값이 절대 출력되지 않습니다 — "N개 값을 불러왔습니다"까지만 나옵니다.
- 값을 다시 발급받고 싶으면 Supabase/Congress.gov에서 새로 받아 같은 파일의 값만 교체하면 됩니다.

## 키가 노출됐을 때 — `SUPABASE_SERVICE_ROLE_KEY` 교체 절차

`service_role` 키는 RLS를 우회하는 전체 관리자 키라서, 어딘가(터미널 기록, 채팅, 잘못된
붙여넣기 등)에 노출됐다고 판단되면 지우는 게 아니라 **새 키를 발급하고 이 키를 쓰는
모든 곳을 한 번에 갱신**해야 합니다. 한 곳이라도 옛 키로 남아 있으면 그 경로는 계속
살아있는 채로 노출된 키가 유효합니다.

1. **Supabase 대시보드** → 이 프로젝트 → Project Settings → API → Project API keys →
   service_role 옆 **Reset** (또는 **Roll**)으로 새 키 발급. 이 순간 옛 키는 즉시 무효화됩니다.
2. **로컬**: `.env.local`의 `SUPABASE_SERVICE_ROLE_KEY=` 값을 새 키로 교체.
3. **GitHub Actions**: 레포 Settings → Secrets and variables → Actions →
   `SUPABASE_SERVICE_ROLE_KEY` 값을 새 키로 갱신 (`.github/workflows/sync-congress.yml`이
   이 이름을 그대로 참조합니다 — 이름 변경 불필요, 값만 교체).
4. **Cloudflare Worker**: `wrangler secret put SUPABASE_SERVICE_ROLE_KEY` 실행 후 새 키
   붙여넣기 (`_worker.js`가 `/api/us/*` 응답에 쓰는 것과 동일한 시크릿).
5. 세 곳(로컬·Actions·Worker) 다 갱신한 뒤, `node scripts/sync-policy-reference-data.js`를
   한 번 실행해 새 키로 정상 동작하는지 확인.

옛 키는 1번 시점에 이미 무효화되므로, 2~4번이 늦어져도 그 사이 옛 키로 데이터가
새어나가진 않습니다 — 다만 그 사이엔 로컬/Actions/Worker가 모두 인증 실패로 멈춥니다.
