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
| T14 | Canada SAD yield + UI | cursor | `yield_model/canada/**`, `canada_*forecast.json`, registry | `cursor/pr-canada-yield` | **review** | SAD+UI+monthly Actions+gov_outlooks; model.yaml → climate_registry |
| T15 | Russia export pulse (PSD+PortWatch) | **cursor** | `scripts/russia_export_pulse/**`, `russia_export_pulse_v1.json` | `cursor/russia-export-pulse` | **review** | 밀 수출·세계비중·기여분 + 보스포루스 보조. 다크십/피격 제외. UI는 Claude 핸드오프. |
| T16 | Phase 2-2 상품×국가 공식 보고서 | **claude** | `scripts/commodity_reports/**`, `_worker.js`, `trade.js`, `style.css` | `claude/phase-2-2-commodity-reports-r5vzqf` | **review** | 본문이 창을 정한다 (USDA의 브라질 밀 보고서 → BRA·밀). 소스 URL 라이브 검증은 세션 네트워크 정책(403 CONNECT)으로 못 함 — 첫 Actions 실행의 `failed feeds:` 보고 enable/disable 정리 필요 |
| T17b | EO 근거 법령 ↔ 법안 연동 (`legal_authorities.linked_bill_id`) | codex | `scripts/lib/public-law-links.js`, `scripts/sync-federal-register.js`, `scripts/sync-public-laws.js` | `codex/eo-public-law-bill-links` | **done** | PR #210 머지됨. `public_law` 타입만 `Pub. L.`/`Public Law` 표기 매칭, usc/constitution은 그대로 외부링크. **주의**: `P.L. 119-45`/`PL 119-45` 축약형은 정규식이 못 잡음 — 실제 동기화 안 돌려본 상태라 실전 영향 미확인. 다음 정상 동기화 후 `data_sync_runs.metadata.public_law_authority_links.citation_unparseable` 값 확인할 것 |
| T17c | dedup 이중 URL 인코딩 버그 6곳 (Congress 3 + Federal Register 3) | codex | `scripts/sync-congress.js`, `scripts/sync-federal-register.js` | `codex/policy-dedup-encoding-fix` | **done** | PR #218 머지됨. `encodeURIComponent`를 `supabaseGet` 쿼리 값에 또 씌워서 공백 있는 값(예: `"Enrolled Bill"`)이 dedup 매칭 실패하던 버그. `119-hr-3377`/`119-hr-7194` 복구 SQL은 `docs/policy-queue-recovery.md` |
| T17d | EO 전용 역사 백필 모드 (`EO_BACKFILL=true`) | codex | `scripts/sync-federal-register.js` | `codex/eo-history-backfill` | **done** | PR #216 머지됨. `presidential_document_type=executive_order`로 좁혀서 규제 안 섞임. 1994~2026 EO 1,557건, 로컬 4페이지로 백필 완료 확인(2026-09-02). 문서: `docs/eo-history-backfill.md` |
| T18 | 법안 AI 유사도 연결 (`bill_relations.relation_origin='semantic'`) | codex | `scripts/sync-congress.js`, `supabase/migrations/20260901_policy_semantic_bill_relations.sql` | `codex/semantic-bill-relations` | **done** | PR #215 머지됨. pgvector RPC `refresh_bill_semantic_relations`, 신규 임베딩 법안만 호출, `source_bill_id` 기준 semantic만 교체(official/verified_manual 안 건드림), 같은 `embedding_model`끼리만 비교, similarity ≥ 0.80 최대 5건, 실패해도 본 동기화는 안 죽음, 단방향. EO는 범위 제외. 마이그레이션 SQL 수동 실행 필요 — 아직 안 했으면 `supabase/migrations/20260901_policy_semantic_bill_relations.sql` SQL Editor에서 한 번 실행할 것 |
| T19 | 정책 UI + `/api/us/*` 배포 | **claude** | `New for anti/policy.js`, `New for anti/index.html`, `New for anti/style.css`, `_worker.js` | `claude/postgresql-requirements-85a9j6` | **review** | PR #202. 법안·EO 백필 상당량 진행됨(EO 1994~2026 완료, 법안 진행 중) — 이제 main에 merge하고 Worker secret(`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`) 등록해서 배포 |
| T20 | 정책 검색 RPC (`search_policy_corpus`) | **codex** | `supabase/migrations/**` (신규) | — | ready | T19의 검색창은 UI/Worker(`/api/us/search`) 배포 완료, Gemini 질의 임베딩까지 정상 동작. `bills`/`executive_orders`/`regulations` 세 테이블(전부 Gemini 임베딩 보유)을 대상으로 코사인 유사도 검색하는 RPC만 없어서 "검색 기능 준비 중"만 뜸. 상세 요청 사양은 `docs/ops/handoff/2026-09-02-claude.md` 참고 |

## 백로그

- 아르헨 norte_soja / chaco skill < 0.20
- 브라질 사탕수수·일부 대두 skill (이미 리치 패널 표기)
- 커스텀 CF 도메인 → `CLOUDFLARE.md`

## 갱신 규칙

1. 작업 시작: `status=in_progress`, branch 칸 채움  
2. 막히면: `blocked` + note에 이유  
3. 끝: `review` 또는 `done` + `./tools/ops/handoff.sh`  
