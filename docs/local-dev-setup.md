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
