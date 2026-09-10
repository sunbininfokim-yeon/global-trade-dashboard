# Japan Macro Kit (`jp_macro_v1`)

DXY 내 비중 2위(~13.6%). 초저금리·YCC·ETF/J-REIT 매입 등 **비전통 정책** 때문에
미국 키트와 다른 고유 지표가 필요하다.

## 카테고리 (칩 순서 = 전 국가 공통 규칙)

| id | 내용 |
|----|------|
| `liquidity` | BOJ 총자산·GDP비·YoY · **JGB 보유비율** · **JGB 매입·롤오버(만기 바)** · **ETF 통합(잔고+비중)** · J-REIT · M2 vs 2019 |
| `rates` | 무담보콜 · JGB 2Y/10Y/30Y · 스프레드 (매입 실적은 유동성 바로 이동) |
| `fx` | USD/JPY · **IMM 엔 순투기** · 외환보유액 · **외환개입** (EUR/JPY·REER 제외) |
| `equity` | Nikkei · TOPIX · 외국인 순매수 · Nikkei VI |
| `growth` | **GDP(YoY\|QoQ)** → **설비투자/GDP · 순자금수요 · GDP 갭** → 노동·춘투 → **PMI는 맨 뒤** |
| `inflation` | 근원 CPI · 근원-근원 · 도쿄 CPI · **CGPI(도매/생산자, 선행 보조)** |

## 2026-08 피드백 반영

- M2 전년비 제거 (vs 2019만 유지)
- ETF 잔고+시장비중 → `boj_etf_holdings` 한 칩
- BOJ 당좌예금 제외 — 초과지준 정보는 유용하나 JGB 보유·매입 실적과 역할이 겹침. **채권 보유비율 + 월간 매입/롤오버 바**가 더 직관적
- JGB 매입 실적 → 만기별 매입 + 롤오버 미실시 막대 (`boj_jgb_ops`). QE/QT국(US/EZ/UK)에도 동일 패턴
- 엔 REER 제거 → IMM 선물 순포지션. EUR/JPY 제거
- 비미국·개입 공표국: 외환개입 칩 (KR/CH/TW 등 stub)

## CGPI가 유의한가?

**보조로 유의하다.** 일본 기업물가(도매·생산자)로, 근원 CPI보다 먼저 움직이는 경우가 많다.
소비 물가(근원/근원-근원)가 메인, CGPI는 “파이프라인 물가” 확인용으로 뒤에 둔다.

## 한계

1. **BOJ ETF 출구** — 잔고는 보이지만 Exit 룰/선례 없음 → 충격 시점·강도 예측 불가  
2. **JGB 가격발견 훼손** — YCC·대규모 매입으로 금리 ≠ 순수 펀더멘털  
3. **개입 단기성** — 미·일 금리차 지속 시 개입 효과는 수일~수주

## 데이터

성장 탭의 아래 세 지표는 `config/japan_growth_v1.json`에 고정한 **공식 스냅샷**이며,
일반 fixture와 구분해 UI에 `official_snapshot`으로 표기한다.

| 지표 | 산식·정본 | 최신 스냅샷 |
|---|---|---|
| `capex_gdp_ratio` | 내각부 ESRI 명목 민간기업 설비투자 ÷ 명목 GDP | 2025년 |
| `net_funding_demand` | BOJ 민간 비금융법인 금융잉여/부족 + 일반정부 금융잉여/부족, 각 4분기 합계 ÷ 동기간 ESRI 명목 GDP | 2026년 1분기 |
| `gdp_gap` | BOJ Output Gap (% of potential GDP) | 2026년 1분기 |

갱신은 공개 원본을 다시 내려받아 스냅샷을 만들고, 통상 매크로 빌드를 실행한다.

```bash
cd "New for anti/scripts/macro_monitor"
python3 build_japan_growth_snapshot.py
python3 build_macro_monitor.py --asof YYYY-MM-DD
```

BOJ 자산·JGB·FX·주가·춘투 등 나머지 일본 지표는 계속 `fixture_synth`다. 다음 후보는
BOJ 통계 · MOF 개입 · CFTC IMM · TSE 수급 · 춘투 연간 시계열이다.
