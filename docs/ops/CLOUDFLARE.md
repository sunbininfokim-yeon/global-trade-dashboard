# Cloudflare 접속 정보

## 알려진 값 (레포에서 확인됨)

| 항목 | 값 | 출처 |
|------|-----|------|
| Worker name | `global-trade-dashboard` | `wrangler.jsonc` |
| Worker URL | `https://global-trade-dashboard.sunbin-info-kim.workers.dev` | `scripts/yield_model/china/*` 등 |
| Assets dir | `New for anti` | wrangler `assets.directory` |
| KV binding | `API_CACHE` | id `35315eb44cfc4cd480c25794c0623c04` |
| Cron | `0 18 * * *` UTC | wrangler triggers |

## 아직 비어 있음 (선택 — 있으면 채워 주세요)

| 항목 | 값 |
|------|-----|
| 커스텀 도메인 | _(예: https://…)_ |
| Cloudflare Pages 프로젝트 (쓰면) | |
| 대시보드 계정 메모 (비비밀) | |
| 추가 KV namespace (brazil_agri 등) | id / binding 이름 |

**필수는 아닙니다.** Worker URL만으로 curl 스모크 테스트와 문서 링크가 가능합니다.  
Pages 전용 URL·커스텀 도메인을 쓰면 여기에 적어 두면 에이전트들이 배포 확인 주소를 맞춥니다.

## 비밀 값 (이 파일에 적지 말 것)

- `CF_API_TOKEN`, Account 전역 키  
- GitHub Secrets 내용  

로컬 확인은 `wrangler whoami` / Cloudflare 대시보드만.
