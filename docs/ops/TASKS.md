# TASKS — 현재 할 일 보드

**2026-08-05:** UI·배포 보드는 Claude Code가 관리한다 (`OWNERS.md` 참조).
각 터미널은 **자기 owner 행만** `status`/`note`를 갱신한다 (`claim.sh` 사용 권장).

상태: `ready` | `in_progress` | `blocked` | `review` | `done`

| id | task | owner | files / scope | branch | status | note |
|----|------|-------|---------------|--------|--------|------|
| T01 | UI 기후 뷰 공용화 | claude | `app.js` 등 | `claude/ui-climate-generic` | **review** | PR #2. **main 머지 전 배포 안 됨** |
| T02 | ops 문서·터미널 스크립트 | cursor | `docs/ops/**`, `tools/ops/**` | `cursor/optimize-audit` | **review** | 소유권 핸드오프 + AUDIT 포함 |
| T07 | 전체 점검·최적화 1차 | cursor | app/ticker/assets/cron/audit | `cursor/optimize-audit` | **review** | 4개국 연결, 티커, icrisat ignore, audit 스크립트. 보고서 `docs/ops/AUDIT_2026-08-04.md` |
| T03 | 데이터 계약 재확인 | codex | `DATA_LAYOUT`, `HANDOFF_PROMPT` | — | ready | 좁은 국가 1개 |
| T04 | 중국 skill 음수 원인 | cursor | `yield_model/china/**` | `cursor/ml-china-skill` | ready | audit: skill −0.5~−1.6, beats_trend false 전원 |
| T04b | 인도네시아 climate_gate 표본 | cursor/codex | `indonesia/**` | — | ready | 19/40 시즌. 게이트·베이스라인 정책 재검토 |
| T04c | 인도 forecast JSON 복구 | cursor | Actions + `public/data/india_*` | — | ready | 파일 missing → `gh workflow run india_yield_forecast` |
| T05 | 논문/사전 자료 검토 | anti | `docs/literature/**` | `anti/lit-…` | ready | 코드 금지 |
| T06 | 코드 리뷰 | claude | PR diff | — | ready | 소유권 이전 후에도 리뷰는 계속 수행 |
| T08 | liquidity/official UI 연결 | cursor | app.js + worker API | — | ready | 스냅샷 JSON은 이미 있음. 패널 미연결 |
| T09 | 기후 UI 우측 제거·좌측 산지·미니범례 | **claude** | `app.js` `style.css` `index.html` `usda_gain_outlook_v1.json` | `claude/ui-climate-panel` | **review** | 우측 제거·미니범례·산지 좌측 완료. 아프리카 참고 패널 유지됨 |
| T11 | 지도 곡률 = 실제 GlobeView 전환 | **claude** | `app.js` `style.css` `index.html` | `claude/ui-globe` | **in_progress** | MapLibre 래스터 베이스맵 제거 → 구체 메시 + 벡터 국가. deck 9.3.7 GlobeView는 Arc/Line/Text 미렌더 → PathLayer + HTML 라벨로 대체. 남극 소스에서 제거 |
| T12 | 국가 포커스 범용화 (하드코딩 제거) | **claude** | `app.js` `data.js` | `claude/ui-globe` | **in_progress** | `resolveCountry()` 레지스트리: 월드 GeoJSON 중심점 + 별칭. `CountriesData` 65개 표는 게이트→오버라이드로 강등. Comtrade 행도 `reporterDesc` 폴백. Angola/Kazakhstan/Mongolia 등 미등록국 클릭 검증 완료 |
| T13 | 기후 국가 드릴다운 = TARGET 워크스페이스 | **claude** | `app.js` `style.css` `index.html` | `claude/ui-globe` | **review** | HUD 프레임 + 산지 라벨(단수·편차) + 단위 환산표 |
| T10 | MENA yield pipeline | cursor | `yield_model/mena/**`, `public/data/mena_yield_forecast.json` | `cursor/ml-mena-yield` | **in_progress** | Nile irrigated + Maghreb rainfed wheat T1; FAOSTAT labels; forecast JSON |
| T14 | Russia climate registry wiring | **cursor** | `yield_model/russia/model.yaml` + `climate_registry_v1.json` | `cursor/russia-yield-review` | **review** | Rosstat wheat/sunflower zones on globe via registry. UA paused. No app.js edit. |

## 백로그

- 아르헨 norte_soja / chaco skill < 0.20
- 브라질 사탕수수·일부 대두 skill (이미 리치 패널 표기)
- 커스텀 CF 도메인 → `CLOUDFLARE.md`

## 갱신 규칙

1. 작업 시작: `status=in_progress`, branch 칸 채움  
2. 막히면: `blocked` + note에 이유  
3. 끝: `review` 또는 `done` + `./tools/ops/handoff.sh`  
