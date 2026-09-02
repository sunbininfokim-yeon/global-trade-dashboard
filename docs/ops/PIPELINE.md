# PIPELINE — Terminal → GitHub → Cloudflare

## 목표 흐름

```text
  로컬 터미널 (Claude / Codex / Cursor / Anti)
            │  git commit + push branch
            ▼
       GitHub (source of truth)
            │  PR merge → main
            │  GitHub Actions (cron / workflow_dispatch)
            ├──────────────────────────────┐
            ▼                              ▼
   static: public/data/*.json      bots → Cloudflare KV
            │                       (brazil_agri 등)
            ▼
   Cloudflare Worker
   name: global-trade-dashboard
   assets: New for anti/
   kv: API_CACHE
   cron: 0 18 * * * (UTC)
            ▼
   https://global-trade-dashboard.sunbin-info-kim.workers.dev
```

## 무엇이 어디에 저장되는가

| 데이터 | 저장소 | 공개 여부 |
|--------|--------|-----------|
| 원본 API 캐시 | 로컬 `scripts/yield_model/cache/` 만 (gitignore) | 비공개·비커밋 |
| training.csv / model.json | **GitHub** `scripts/yield_model/` | 저장소 권한 따름 |
| 대시보드 forecast JSON | **GitHub** → deploy → **CF static** `public/data/` | 방문자 fetch |
| 무역 proxy 캐시 | **Cloudflare KV** `API_CACHE` | Worker `/api/*` 경유 |
| CONAB/Brazil bot 스냅샷 | CF KV (Actions secrets: `CF_*`) | API |

로컬 맥북을 **장기 데이터 창고로 쓰지 않는다.**  
실험 후 커밋할 산출물만 남기고, 캐시는 언제든 삭제 가능해야 한다.

## 배포가 안 될 때 (이미 겪은 실패)

1. **작업 브랜치에만 커밋하고 main을 push** → “Everything up-to-date”, 사이트 무변  
   - 해결: 작업 브랜치를 push → PR merge → main 배포
2. Worker 없이 static만 배포 → `/api/*` 404  
   - `wrangler.jsonc` 의 `"main": "_worker.js"` 유지
3. 좌표를 무역용 CountriesData에서만 조회 → 산지 점 소실  
   - 국가 패널 좌표는 설정에 인라인 (DATA_LAYOUT 참고)

## GitHub Actions (현재 레포)

`.github/workflows/` 예:

- `daily_update.yml` — Brazil agri bot → CF KV  
- `*_yield_forecast.yml` — 국가별 예측 갱신  
- `update_data.yml`, `shipping_capacity_update.yml`, ICRISAT 관련 등  
- `commodity_news_ticker.yml` — 속보 30분 · `macro_liquidity_intel.yml` — 6h · `official_reports.yml` — 4h  
- `commodity_reports.yml` — 4h · 상품 × 국가 공식 보고서 (`/api/commodity-reports`, 2단계 국가 창)  

**주기·저장·학습 전략 정본:** [`DATA_CADENCE.md`](./DATA_CADENCE.md)  
(위성·기상·주식·정부 릴리스 캘린더·티커 권장 interval 포함)

로컬에서 수동 실행 예:

```bash
gh workflow list
gh workflow run daily_update.yml
gh run list --limit 5
```

Secrets (GitHub repo Settings, **커밋 금지**):

- `CF_ACCOUNT_ID`, `CF_KV_NAMESPACE_ID`, `CF_API_TOKEN`
- 기타 외부 API 키

## 에이전트 체크리스트 (머지 전)

- [ ] `OWNERS.md` 범위만 수정했는가  
- [ ] forecast JSON이면 `DATA_LAYOUT.md` 필드 충족  
- [ ] 캐시·`.env`·시크릿 없음  
- [ ] 브랜치 remote push 됨  
- [ ] PR 본문에 `docs/ops/TASKS.md` id 링크  

## 배포 확인

```bash
# 워커 응답
curl -sI "https://global-trade-dashboard.sunbin-info-kim.workers.dev" | head -5

# 예측 파일 (경로는 사이트 구조에 맞게 조정)
curl -s "https://global-trade-dashboard.sunbin-info-kim.workers.dev/public/data/brazil_yield_forecast.json" | head -c 200
```

커스텀 도메인이 있으면 위 URL을 그 도메인으로 바꿔 `CLOUDFLARE.md`에 적는다.
