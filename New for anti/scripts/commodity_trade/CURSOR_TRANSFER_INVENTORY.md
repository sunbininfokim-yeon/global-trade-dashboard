# Commodity Trade — Cursor 이관 인벤토리 (Grok → 로컬 레포)

**작성:** 2026-08-13 (대화 기준 작업일은 2026-08-09)

**로컬 레포 목표 경로:** `/Users/yeoninair/Documents/New for anti-dart`

**워크스페이스 경로 (이 환경):** `artifacts/New for anti/`

이 문서는 코드를 다시 쓰기 전에 **존재하는 자산만** 보고한다. 없는 것은 `없음`으로 명시한다.

---

## 0. 학습 모델 (ML)

| 항목 | 상태 |
|------|------|
| training data / feature 정의 / 학습 코드 / 계수 / 평가 결과 | **없음** |
| 주장·생성 금지 | 무역 파이프는 통계 어댑터 + 집계만. 예측 모델 없음 |

---

## 1. 이관 인벤토리 표

| 자산 | 원래 경로/출처 | 목적 | 입력 | 출력 | 출처/라이선스 | 최신 관측월 | 재생성 방법 | 검증 상태 |
|------|----------------|------|------|------|---------------|-------------|-------------|-----------|
| `build_monthly.py` | `scripts/commodity_trade/build_monthly.py` | energy→minerals→agri 오케스트레이션, trailing 12m, board stage2 갱신 | 어댑터 series | `commodity_trade_monthly_v1.json` + board 일부 필드 | 내부 | 빌드 시점 | `python3 build_monthly.py --sectors energy,minerals,agri_trade` | P0 완료: ISO3 계약 검증, 부분 빌드 보존, 원자적 저장, `--no-fetch` / `--print-stats`, 호출 상한형 Comtrade 월별 overlay. P1 완료: 질량 kg 정규화·단위/프록시/최신성 품질 메타데이터 |
| `hs_match.py` | 동 폴더 | HS same/parent/child/alias/incompatible | 코드 문자열 | relation + commodity resolve | 내부 | n/a | import | 수동 검증 |
| `world_link.py` | 동 폴더 | `link_country_world_v1` identity/contributor/partial_sum/incomparable | country points | nodes/edges/shares | 내부 | n/a | import | 대두 BRA+USA share 수동 확인됨 |
| `sources/jodi_oil.py` | sources/ | 원유·석유제품 월별 수출 | JODI CSV (캐시 `/tmp/commodity_trade_cache`) | series by country | JODI (공개) | 빌드 시 ~2026-05 | 어댑터 fetch | 네트워크 의존; `KTONS`는 1,000 metric tons로 kg 정규화 |
| `sources/jodi_gas.py` | sources/ | LNG 월별 수출 | JODI Gas | series lng | JODI (공개) | ~2026-06 | 어댑터 fetch | 동상 |
| `sources/brazil_comexstat.py` | sources/ | 광물+농 BRA 수출 kg (NCM→HS4) | `EXP_{year}.csv` MDIC | series | 브라질 정부 공개 | 2026-07 | 연 CSV 다운로드 후 집계 | SSL 우회 필요 이력; 캐시 비커밋 |
| `sources/cochilco_copper.py` | sources/ | 칠레 구리 선적 kMT | Cochilco 월보 HTML | copper/CHL | Cochilco 공개 | 2026-02 | HTML 파싱 (xlsx 404) | 파싱 의존, 깨지기 쉬움 |
| `sources/abs_metal_ore.py` | sources/ | 호주 Metal Ore Mining FOB **프록시** | ABS 5368032a xlsx | iron_ore/AUS AUD_million | ABS | 2026-06 | xlsx 다운로드 | **톤 아님**, industry proxy |
| `sources/usa_ers_agri.py` | sources/ | 미국 대두·옥수수·밀·면화 수출 World total | ERS FATUS top-10 xlsx | USA metric_tons | USDA ERS | 2026-06 | xlsx 파싱 | “World total”=미국 대세계 수출 |
| `sources/comtrade.py` | sources/ | UN Comtrade monthly (옵션) | env `COMTRADE_SUBSCRIPTION_KEY` | series | UN Comtrade | 키·쿼터 의존 | data API | **키를 파일에 저장하지 말 것**. 2026-08-09 쿼터 소진 확인 |
| `build_comtrade_priority_monthly.py` + `priority_universe.py` | scripts/commodity_trade/ | 핵심 보고국 27개 × 핵심 HS 23개, World 상대 수출입 월별 Preview 패널 | Comtrade free Preview (한 월/요청) | `commodity_trade_comtrade_priority_v1.json` | UN Comtrade | 국가별 상이 | 호출 상한·캐시로 점진 수집 | P2 완료: 전체 세계 커버리지 아님, 추정·보고 상태 플래그 보존. 공개 Preview가 비어도 무역 0으로 해석하지 않음 |
| `build_national_priority_monthly.py` + 국가 어댑터 | scripts/commodity_trade/ | Preview 공백국의 공식 월간 원천 패널 | 인도·멕시코·노르웨이·사우디·태국 공식 공개 원천 | `commodity_trade_national_priority_v1.json` | 각국 정부 | 국가별 상이 | HS 계약·캐시·호출 상한 | 사우디는 공개 Tableau HS4 value/weight를 추가. 최신 상세표가 요청월보다 오래되면 마지막 12개월을 보존하고 stale로 표시 |
| `sources/saudi_gastat_tableau.py` | sources/ | 사우디 월별 HS4 수출입 World total | GASTAT 공개 Tableau CSV | SAU metric_tons + million SAR | GASTAT 공개 | 검증된 표는 2025-09까지 | `build_national_priority_monthly.py --reporters SAU` | API 키 불필요. HS6·상대국별 레이블은 자동화하지 않으며, 빈 표를 0으로 변환하지 않음 |
| `national_source_registry.py` | scripts/commodity_trade/ | 공백국의 자동화 가능 여부·품목 계약 기록 | 공식 출처 접근 조건 | 국가 원천 패널 내 registry | 각국 정부 | 출처별 | 코드 검토 | CHN=정확 HS 자동경로 미확정; KOR만 API 키 필요; SAU=공개 Tableau HS4; ARE=식별된 공개 데이터는 2023까지; IDN=공개 월간물 HS2 중심 |
| `commodity_trade_board_v1.json` | `public/data/` | UI 계약 stage1/2, 28 상품, uranium 포함 | 수동+빌드 갱신 | UI | 내부 계약 | as_of 2026-08-09 | 보드 파일 유지, stage2 필드는 build가 갱신 | JSON valid |
| `commodity_trade_monthly_v1.json` | `public/data/` | 월별 포인트 | 빌드 | UI stage2 | 혼합 출처 | 품목별 | `python3 build_monthly.py --sectors energy,minerals,agri_trade` | 마지막 확인본은 energy·minerals·agri_trade 세 섹터를 모두 보유. 원천 갱신 뒤 full rebuild 필요 |
| `commodity_trade_national_priority_v1.json` | `public/data/` | 공식 국가 원천 월별 패널 | 국가별 어댑터 | 향후 Stage2 원천 선택 입력 | 혼합 출처 | 국가별 | `python3 build_national_priority_monthly.py --reporters SAU --max-requests 12` | Preview 파일과 분리. 현재 IND·NOR·THA·MEX·SAU가 있으며, 국가·품목·원본단위·최신월을 명시 |
| `export_controls_v1.json` | `public/data/` | 수출통제 + 색 티어 | 수동 큐레이션 | stage1 색 | 정책·공시 요약 | as_of 2026-08-09 | 파일 편집 | levels: prohibited/restricted/watch (UI는 관찰/주의/경계 매핑) |
| `comtrade_public_seed_v1.json` | `public/data/` | public preview 부분 시드 | public API | 소수 월 | Comtrade public | 1–2개월 조각 | 재수집 가능하나 rate limit | IDN/MYS palm, USA soy/corn/wheat, THA rice **부분** |
| `README.md` | scripts/commodity_trade/ | 실행·HS·소스 요약 | n/a | 문서 | 내부 | n/a | 유지 | 구버전(JODI+Comtrade 중심) — 이 인벤토리로 보강 |
| `config/` | scripts/commodity_trade/config/ | 설정 자리 | — | — | — | — | — | **비어 있음** |
| tests / fixtures | `scripts/commodity_trade/tests/` | 어댑터·정규화 회귀 검증 | 단위 테스트 | — | 내부 | n/a | `python3 -m unittest discover -s tests -v` | 사우디 Tableau CSV 파서·stale fallback·KTONS 환산 회귀 테스트 포함; 네트워크 fixture는 아직 없음 |
| `mineral_trade_stage2/` HANDOFF | 대화 핸드오프 | 34/34 스냅샷 예정이었음 | — | — | — | — | — | **워크스페이스에 폴더 없음** (미제공) |
| 인니 니켈 월별 어댑터 | 조사만 | BPS/세관 | — | — | — | — | — | **코드 없음** |
| 호주 철광 **톤** 시리즈 | 조사만 | ABS 수량 | — | — | — | — | — | **없음** (FOB 프록시만) |
| 대형 `/tmp/commodity_trade_cache` | 런타임 | CSV/xlsx 캐시 | 네트워크 | 로컬 캐시 | 각 출처 | — | 재다운로드 | **커밋 금지** |

---

## 2. 누락 체크리스트 (프롬프트 대조)

| 항목 | 상태 |
|------|------|
| JODI Oil/Gas: crude / petroleum_products / lng | 코드 있음. monthly JSON은 **재빌드 전 agri-only**라 산출에 없음 → full rebuild 필요 |
| Brazil ComexStat | 코드 있음 (광물+농 HS stems) |
| Chile Cochilco copper | 코드 있음 |
| Australia ABS iron-ore FOB proxy | 코드 있음 (톤 아님) |
| USA ERS soy/corn/wheat/cotton | 코드 있음 |
| Comtrade adapter + public seed JSON | 둘 다 있음. Data API 쿼터 제한 문서화 |
| IDN·MYS 팜유, THA 쌀 | public seed 부분만; 전용 어댑터 없음 |
| IDN 니켈 | **없음** (조사·보류) |
| 호주 철광 톤 | **없음** |
| `world_link.py` / link_country_world_v1 | 있음 |
| 수출통제 | `export_controls_v1.json` 있음 |
| 실패/보류 | Comtrade 쿼터; Cochilco xlsx 404; ABS 톤 부재; mineral_trade_stage2 미제공; monthly overwrite agri-only |
| 테스트 fixture | **없음** |
| 학습 모델 | **없음** |

---

## 3. 데이터 계약 (보존)

### Stage
- Stage 1: 국가 × 연도 + 수출통제 색 (작황 모니터 티어와 색 정렬)
- Stage 2: 최신 가용월 기준 trailing 12개월, 기본 월 = 최신
- 작황/수율 뷰와 분리
- 에너지에 uranium 보드 항목 포함 (월별 시리즈는 주로 JODI 3종)

### world_link
- identity / contributor / partial_sum_proxy / incomparable
- 이질 단위 합산 금지
- BRA ≠ 세계; USA ERS World total = 미국 대세계 수출

### 정직성
- null + reason; partial/proxy 표기
- 키는 env만; JSON·로그에 키 금지
- public seed ≠ Data API 결과

---

## 4. 수정 허용 / 금지 (Cursor)

**허용**
- `New for anti/scripts/commodity_trade/**`
- `New for anti/public/data/commodity_trade_board_v1.json`
- `New for anti/public/data/commodity_trade_monthly_v1.json`
- `New for anti/public/data/export_controls_v1.json`
- `New for anti/public/data/comtrade_public_seed_v1.json` (선택)
- 최소 테스트/문서

**금지**
- app.js, style.css, index.html, data.js, shipping.js
- _worker.js, wrangler, .github/workflows, docs/ops, climate_registry, admin1, .gitignore
- main 직접 push, 기존 무관 데이터 삭제, 키·대형 캐시 커밋

---

## 5. Cursor가 로컬에서 할 일 (권장 순서)

1. 이 폴더 트리와 `public/data` 4개 JSON이 로컬 레포에 있는지 확인 (없면 이 워크스페이스/`artifacts`에서 복사).
2. P0 완료: `--no-fetch --print-stats`로 캐시·기존 JSON의 계약/통계를 네트워크 없이 점검한다.
3. 최소 synthetic points로 ISO3·보드 계약·Comtrade 호출 상한 단위 테스트를 추가했다. world_link fixture는 후속 과제다.
4. **Full rebuild** (네트워크 가능한 환경):
   ```bash
   cd "New for anti/scripts/commodity_trade"
   python3 build_monthly.py --sectors energy,minerals,agri_trade
   ```
   → monthly JSON에 energy+minerals+agri 모두 복구.
5. 검증:
   ```bash
   python3 -m json.tool ../../public/data/commodity_trade_board_v1.json >/dev/null
   python3 -m json.tool ../../public/data/commodity_trade_monthly_v1.json >/dev/null
   python3 -m json.tool ../../public/data/export_controls_v1.json >/dev/null
   git diff --check
   git status
   ```
6. Comtrade: 쿼터 회복 후에만 소량 호출. 대량 수집으로 쿼터 소진하지 말 것.

---

## 6. 복사 대상 파일 목록 (누락 없이)

```
scripts/commodity_trade/README.md
scripts/commodity_trade/CURSOR_TRANSFER_INVENTORY.md   # 본 문서
scripts/commodity_trade/__init__.py
scripts/commodity_trade/build_monthly.py
scripts/commodity_trade/hs_match.py
scripts/commodity_trade/world_link.py
scripts/commodity_trade/sources/__init__.py
scripts/commodity_trade/sources/jodi_oil.py
scripts/commodity_trade/sources/jodi_gas.py
scripts/commodity_trade/sources/brazil_comexstat.py
scripts/commodity_trade/sources/cochilco_copper.py
scripts/commodity_trade/sources/abs_metal_ore.py
scripts/commodity_trade/sources/usa_ers_agri.py
scripts/commodity_trade/sources/comtrade.py
public/data/commodity_trade_board_v1.json
public/data/commodity_trade_monthly_v1.json
public/data/export_controls_v1.json
public/data/comtrade_public_seed_v1.json
```

`__pycache__/` 및 `/tmp/commodity_trade_cache/**` 는 복사·커밋하지 않는다.

---

## 7. Known limitations (한 줄씩)

- monthly JSON이 agri-only로 덮였음 → full rebuild 필수
- Comtrade free quota 소진 이력; public seed는 불완전
- Cochilco는 HTML 파싱 (공식 xlsx 링크 404)
- AUS iron_ore는 AUD FOB industry proxy
- config/ 및 tests 공란
- mineral_trade_stage2 핸드오프 폴더는 한 번도 워크스페이스에 없음
