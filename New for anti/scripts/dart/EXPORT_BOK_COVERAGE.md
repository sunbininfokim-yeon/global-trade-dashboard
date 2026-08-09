# 수출 15·20대 × 한은 KSIC 커버리지

생성: `python3 tools/gen_industry_kits.py`  
산출: `config/industry_kits.json`, `config/export_bok_coverage.json`

## MOTIE 기존 15대 주력 수출 품목 → 키트

| MTI 품목 | kit id | 대표 KSIC |
|----------|--------|-----------|
| 반도체 | `semiconductor` | C261 |
| 자동차 | `auto` | C30 |
| 일반기계 | `machinery` | C29 |
| 석유화학 | `petrochemical` | C20 |
| 석유제품 | `petroleum_products` | C19 |
| 철강 | `steel` | C241 |
| 디스플레이 | `display` | C262 |
| 자동차부품 | `auto_parts` | C303 |
| 선박 | `shipbuilding` | C311 |
| 컴퓨터 | `computers` | C263 |
| 무선통신 | `telecom_devices` | C264 |
| 섬유 | `textile` | C13, C14 |
| 바이오헬스 | `biohealth` | C21 |
| 이차전지 | `battery` | C282 |
| 가전 | `home_appliances` | C285 |

출처: 산업통상자원부 주력 수출 품목 체계 (조선일보·머니투데이 등 2026-05 보도에서 15대 목록 확인).

## 2026년 추가 5개 (20대)

| MTI | kit |
|-----|-----|
| 전기기기 | `electrical_equipment` |
| 비철금속 | `nonferrous` |
| 농수산식품 | `food_agri` |
| 화장품 | `cosmetics` |
| 생활용품 | `household_goods` |

출처: 산업부 MTI 개정·주력품목 15→20 확대 보도자료.

## 한은 기업경영분석 KSIC 중분류

`export_bok_coverage.json`의 `bok_ksic_midclass_map`에  
제조 C10–C33 + 유틸 D35 + 건설 F + 도소매 G + 운수 H49–H52 를 키트에 매핑.

- 한은은 **KSIC 제11차** 기준으로 업종별 평균 재무비율을 공표.
- 매칭 규칙: **가장 긴 KSIC prefix 우선** (예: `C261` → 반도체, `C26` → 전자부품 일반).

해운(`H50`)·항공(`H51`)은 수출 15대는 아니나 선박 밸류체인·IFRS16 특성상 키트 포함.

## 키트 개수

생성 스크립트 기준 약 **31개** 키트 (general·manufacturing_other 폴백 포함).

전제·이유: `INDUSTRY_RATIONALE.md` (전자·조선·해운 심층) + 각 키트 `notes_ko`/`sources`.
