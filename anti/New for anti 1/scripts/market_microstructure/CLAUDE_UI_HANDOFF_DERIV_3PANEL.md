# Claude UI — 파생상품 3분할 + 클릭 드릴다운 (2026-08-08)

Cursor 엔진/JSON은 main에 있음. **아래는 UI 재구성 요청.**

## 사이트에서 본 것 (live)

금융 → 옵션·공매도 동향 = `시장 미시구조` 패널이 **이미 연결됨**.
다만:

1. 조기경보가 **「높음·하방」만 크고**, *왜*인지(P/C·숏 실측)가 한눈에 안 보임  
2. 채널 박스·표 행이 **클릭되지 않음** (div, onclick 없음)  
3. 파생이 **한 스크롤 나열** — 선빈 요청 3분할 구조 아님  
4. 가격×수급은 표/요약은 있으나 **인포맥스형 막대 분포 차트**는 약함  

→ 데이터가 틀린 게 아니라 **UI가 엔진 계약을 덜 풀어쓴 상태**.  
(로컬 worktree `app.js`는 옛 placeholder일 수 있음 — **배포본/main 기준**으로 볼 것.)

## 파생상품 내부 3탭 (필수)

### ① 한국 수급이 얼마나 꼬였나
JSON: `market_microstructure_v1.json` + `kospi_concentration_history_v1.json` + `ai_casino_brief_v1.json`

- 코스피 Conc_top2/5/10 차트
- **종목 선택** (단일종목 LETF 있는 이름 중심: 하닉·삼전 + `stocks[].products` 있는 종목)
- 선택 종목: LETF 거래대금/현물 비율(`letf_turnover_ratio` 등), 상품별 **AUM·거래대금** (`products[].aum`, `trading_value`)
- NAV 필드가 없으면 AUM만 표시 + “NAV 미제공” (가짜 NAV 금지)

### ② 외국인·개인이 어느 가격에서 샀나 (인포맥스형)
JSON: `investor_price_levels_v1.json`

- **코스피 지수**: `kospi_index_levels.bins_by_close` → 레벨×주체 **막대**
- **개별주**: 종목 선택 → `tickers[code].bins_by_close` 막대 + `close_day_table_*`
- 실측만. `quality=missing`면 빈칸

### ③ 미국 → 한국 조기경보
JSON: `us_kr_transmission_v1.json` (+ `us_regime_v1.json`)

필수 표시:

- `headline_ko` / `why_ko` (Cursor가 보강: P/C·숏 실측 근거 문장)
- `evidence_us[]` 표 (심볼, P/C vol, P/C OI, short_chg%)
- `channels.*.drivers` — KR 타깃 칩
- 카드/행 **클릭 → 모달 표** (`ui_hint_ko` 참고)

하방 ≠ 미국 주가 급락. **풋 우세 옵션 레짐 × KR 링크 heat**.

## 클릭 동작 (전 박스)

요약 카드·채널 카드·표 행·Conc 포인트 → 클릭 시 상세 표/차트.
클릭 불가하면 “데이터만 있고 설명 없음”으로 보임.

## Cursor가 이미 가진 것 / 없는 것

| 요청 | Cursor | Claude |
|------|--------|--------|
| Conc·단일종목 LETF AUM/TV | ✅ `market_microstructure_v1` | 종목 셀렉터+표 UI |
| 인포맥스 가격대 분포 데이터 | ✅ `investor_price_levels_v1` | 막대 차트+종목 전환 |
| US→KR heat·drivers | ✅ transmission | why/evidence 노출+클릭 |
| why_ko / evidence_us | ✅ 엔진 보강함 | 렌더 |
| 박스 클릭 모달 | ❌ (UI) | ✅ 구현 |
| 3탭 IA | ❌ (UI) | ✅ 구현 |
| 틱 단위 누가·어느호가 | ❌ 공개데이터 없음 | 배지로 명시 |
| KR 파생 외인 콜/풋 분리 | △ CSV/KRX_API | missing 배지 |

## 붙여넣기

```
Read CLAUDE_UI_HANDOFF.md + CLAUDE_UI_HANDOFF_DERIV_3PANEL.md
금융→파생을 3탭으로: (1) KR 꼬임/Conc/단일종목 LETF (2) 인포맥스형 가격대 수급 차트 (3) US→KR 조기경보 with why_ko+evidence_us
모든 요약 박스/행 클릭→상세 표. 가짜 숫자 금지. 배포본 app.js 기준.
```
