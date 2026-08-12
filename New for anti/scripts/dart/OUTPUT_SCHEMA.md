# KFA Engine Output Design — `dart-company-v2`

**Audience:** Cursor (engine) · Claude (UI/Worker) · 데이터 소비자  
**Status:** design (구현 가이드). 현행 런타임은 아직 `dart-company-v1` + `fundamental_pack` 병행.  
**원칙:** 숫자는 공시·시세에서만. 없으면 `null` + `reason`. LLM 없음. 투자의견 필드 금지.

---

## 1. 목표

| 소비자 | 읽어야 할 것 |
|--------|----------------|
| **금융 란 UI (원페이저)** | `desk` 만으로 충분 |
| **취준/교육 모드** | **`levels.beginner`** |
| **투자 상세** | **`levels.investor`** (+ `desk` / `market`) |
| **M&A/실사** | **`levels.ma`** (+ `bridges` / `slots`) |
| **DCF 입력 UI** | `valuation.assumptions_seed` + `valuation.scenarios` |
| **유니버스 스크리너** | `summary` (경량) |
| **디버그/감사** | `statements` + `validation` + `provenance` |

한 JSON에 다 넣되, **UI는 `levels` 탭으로만** 읽게 한다. 원시 `metrics` 전체를 화면에 뿌리지 않는다.

**단계 공개 설계 정본:** [`LEVELS_OUTPUT.md`](./LEVELS_OUTPUT.md)

---

## 2. 최상위 골격

```jsonc
{
  "schema_version": "dart-company-v2",
  "engine_version": "kfa-2.0.0",
  "generated_at": "ISO-8601Z",
  "disclaimer_ko": "…",
  "source": { "kind": "sec_companyfacts|opendart|fixture", "asof": "…", "cache": true },

  "issuer": { /* 기업 식별 */ },
  "period": { /* 보고 기간 */ },
  "quality": { /* 파싱·BS 검증 게이트 */ },

  "statements": { /* L1 계정 — 당기+추세 */ },
  "ratios": { /* L2 비율 카탈로그 */ },
  "bridges": { /* 현금·레버리지 브리지 */ },
  "industry": { /* 키트·peer·플래그 */ },

  "desk": { /* ★ 현업 원페이저 = fundamental_pack 승격 */ },
  "market": { /* 시세·배수 — optional */ },
  "valuation": { /* 가정 DCF — optional */ },

  "levels": {
    "beginner": { /* 취준/기초 — LEVELS_OUTPUT.md */ },
    "investor": { /* 주식 — beginner 상속 + 현금·레버리지·시세 */ },
    "ma": { /* M&A — investor 상속 + L3 slots */ }
  },

  "narrative": { /* 규칙 문장 — 구조화 */ },
  "summary": { /* 스크리너 1행 */ },
  "provenance": { /* 계정 매칭 감사 */ }
}
```

### v1 → v2 매핑

| v1 | v2 |
|----|----|
| `corp` | `issuer` |
| `parse_status` + `validation` | `quality` |
| `accounts` | `statements.accounts` (+ `statements.series`) |
| `metrics` | `ratios.metrics` |
| `ma_metrics` | `bridges` + 일부 `ratios` |
| `fundamental_pack` | **`desk`** (단일 진입점) |
| `market` | `market` (동일, 정규화) |
| `valuation` + `assumption_defaults` | `valuation` |
| `narrative[]` | `narrative.bullets[]` + `narrative.by_lens` |
| `scores` (빈 객체) | 삭제 → `desk.scorecard` |
| `macro_beta` (빈 객체) | 후순위 / 제거 |

---

## 3. 블록별 계약

### 3.1 `issuer`

```jsonc
{
  "ticker": "CAT",              // 표시용
  "name": "CATERPILLAR INC",
  "corp_code": "0000018230",    // DART corp_code 또는 SEC CIK (0-pad)
  "exchange_hint": "NYSE",      // optional
  "country": "US",              // US|KR
  "currency": "USD",
  "industry": {
    "kit_id": "machinery",
    "ksic": "C291",             // KR 벤치마크용; US는 매핑 힌트
    "label_ko": "일반기계"
  },
  "shares_out": 465287332.0     // null 가능
}
```

### 3.2 `period`

```jsonc
{
  "fiscal_year": 2025,
  "fiscal_period": "FY",
  "report_code": "10-K",        // or DART 11011
  "fs_div": "CFS",              // consolidated
  "period_end": "2025-12-31",   // 가능하면
  "units_note": "USD absolute"  // KR은 원 단위 명시
}
```

### 3.3 `quality` (게이트 — UI 배지)

```jsonc
{
  "parse_status": "verified|unverified|partial",
  "identity_ok": true,
  "checks": [
    { "id": "assets_eq_liab_plus_equity", "ok": true, "rel_error": 0.0 }
  ],
  "coverage": {
    "revenue": true,
    "cogs": true,
    "cfo": true,
    "capex": true,
    "interest_bearing_debt": true,
    "marketable_securities": false
  },
  "warnings_ko": []
}
```

`parse_status != verified` 이면 UI는 경고 배지 + desk는 읽되 강조 축소.

### 3.4 `statements` (L1)

계정은 **표준 ID만** 노출. 매칭 디테일은 `provenance`.

```jsonc
{
  "accounts": {
    "REVENUE": { "value": 67589e6, "unit": "currency" },
    "COGS": { "value": 44752e6, "unit": "currency" },
    "CAPEX": { "value": 2821e6, "unit": "currency", "sign_convention": "outflow_positive" }
  },
  "series": {
    // 열: y_2, y_1, y_0 (older → newer). 길이 3 기본, 이후 5년 확장 시 y_4…y_0
    "REVENUE": [67060e6, 64809e6, 67589e6],
    "OPERATING_INCOME": [12966e6, 13072e6, 11151e6],
    "NET_INCOME": [10332e6, 10788e6, 8882e6],
    "CFO": [null, null, 11739e6],
    "FCF": [11288e6, 10047e6, 8918e6]
  }
}
```

**규칙**
- Capex: 엔진 내부는 `FCF = CFO − |Capex|`. 출력에 `sign_convention` 명시.
- 없는 계정: 키 생략 **또는** `{ "value": null, "reason": "missing" }` — v2는 **키 유지 + null** 권장(UI 스키마 고정).

### 3.5 `ratios` (L2 카탈로그)

```jsonc
{
  "metrics": {
    "operating_margin": {
      "value": 16.4982,
      "unit": "pct",           // pct | x | currency
      "label_ko": "영업이익률",
      "polarity": "higher_better",
      "trend_3y": [19.33, 20.17, 16.50],
      "yoy": -3.67,
      "yoy_unit": "pp",         // pct | pp | Δ
      "level": "investor",      // beginner|investor|ma|desk
      "reason": null
    }
  },
  "index_by_level": {
    "beginner": ["current_ratio", "debt_ratio", "roe", "operating_margin", "net_margin"],
    "investor": ["fcf", "earnings_quality", "net_debt_to_ebitda", "inventory_turnover", "roa"],
    "ma": ["fcf_margin", "ebitda_proxy", "gross_interest_bearing_debt", "lease_to_liabilities"]
  }
}
```

비율 정의 단일 소스: `config/metrics.spec.json` + `bridges` 파생.

### 3.6 `bridges` (실무 핵심 — 중복 제거)

`ma_metrics`를 브리지 중심으로 재편.

```jsonc
{
  "cash": {
    "cfo": 11739e6,
    "capex_abs": 2821e6,
    "fcf": 8918e6,
    "fcf_margin_pct": 13.19,
    "cfo_to_ni": 1.32
  },
  "leverage": {
    "gross_interest_bearing_debt": 36210e6,
    "cash_and_marketable_securities": 9980e6,
    "net_debt": 26230e6,
    "net_debt_incl_lease": 26958e6,
    "ebitda_proxy": 13413e6,
    "net_debt_to_ebitda": 1.96,
    "definition_ko": "이자부차입 − (현금+시장성유가증권)"
  },
  "legacy": {
    "net_debt_ncl_minus_cash": { "value": …, "deprecated": true }
  }
}
```

### 3.7 `industry`

```jsonc
{
  "kit_id": "machinery",
  "label_ko": "일반기계",
  "flags": [
    { "id": "finance_sub_leverage_distortion", "severity_ko": "…", "severity": "watch" }
  ],
  "adjusted_metrics": { "debt_ratio_ex_lease": { "value": 359.0, "unit": "pct" } },
  "peer": {
    "kind": "bok_ksic",          // bok_ksic | none | us_peer_future
    "asof": "2024",
    "label_ko": "일반 목적용 기계",
    "vs": [
      { "metric": "net_margin", "firm": 13.14, "peer": 5.13, "delta": 8.01, "unit": "pp", "read": "above_peer" }
    ],
    "caveat_ko": "미국 발행사에 한은 평균은 구조 참고용이지 peer valuation 아님"
  },
  "notes_ko": ["…"]
}
```

### 3.8 `desk` ★ (UI 기본 화면)

현 `fundamental_pack`을 정식 이름으로 승격. **금융 란 첫 페인트 = `desk`만.**

```jsonc
{
  "schema_version": "kfa-desk-1.0.0",
  "headline_ko": "CAT: 매출 YoY +4.3%, OPM 16.5%, ND/EBITDA 1.96x, FCF+",
  "scorecard": [
    {
      "id": "growth|profitability|cash_conversion|leverage|returns",
      "label_ko": "성장",
      "status": "ok|watch|risk|n/a",
      "primary": { "revenue_yoy_pct": 4.29, "ni_yoy_pct": -17.67 },
      "lens_ko": "Equity: …"
    }
  ],
  "trend_table": {
    "columns": ["y_2", "y_1", "y_0"],
    "columns_ko": ["2년전", "1년전", "당기"],
    "rows": [
      { "id": "revenue", "label": "Revenue", "unit": "currency", "values": […], "yoy": 4.29, "yoy_unit": "pct" }
    ]
  },
  "cash_bridge": { /* = bridges.cash */ },
  "leverage_bridge": { /* = bridges.leverage */ },
  "market_snapshot": { "price": 856.96, "per": 44.9, "ev_ebitda": 31.7, "available": true },
  "valuation_snapshot": {
    "dcf_mid_per_share": 232.1,
    "dcf_band_per_share": [91.0, 452.3],
    "vs_market_pct": -72.9,
    "note_ko": "가정 밴드 ≠ 목표가"
  },
  "desk_notes_ko": ["금융자회사 착시…"],
  "method_ko": ["1) 성장·마진…", "2) 현금전환…", "3) ND/EBITDA…", "4) 배수·DCF…", "5) 업종 왜곡…"]
}
```

`status` 의미 (엔진 규칙, 신용등급 아님):
- `ok` — 데스크 기본 통과
- `watch` — 추세/레벨 이상 징후
- `risk` — 현금·레버리지 적신호
- `n/a` — 입력 부족

### 3.9 `market` (optional)

```jsonc
{
  "ok": true,
  "quote": {
    "ticker": "CAT",
    "price": 856.96,
    "currency": "USD",
    "asof_unix": 1786046402,
    "provider": "yahoo_chart"
  },
  "multiples": {
    "market_cap": 3.987e11,
    "per": 44.89,              // mcap / NI (TTM filing FY)
    "pbr": 18.70,
    "ev": 4.250e11,            // mcap + net_debt
    "ev_ebitda": 31.68,
    "reasons": {}
  }
}
```

시세 실패 시: `{ "ok": false, "reason": "…" }` — desk.market_snapshot.available=false.

### 3.10 `valuation` (optional, 가정 모형)

```jsonc
{
  "schema_version": "dart-valuation-v1",
  "disclaimer_ko": "…",
  "assumptions_seed": {
    "from_statements": {
      "capex_to_sales": 0.0417,
      "da_to_sales": 0.0335,
      "sales_to_nwc": 0.2356,
      "tax_rate": null,
      "ebit_margin": 0.165,
      "quality_tier": "quality_compounder"
    },
    "presets": {
      "bear|base|bull": { /* 전체 assumption 세트 */ }
    }
  },
  "scenarios": [
    {
      "id": "base",
      "name_ko": "기본(공시 시드)",
      "assumptions": { "wacc": 0.085, "revenue_cagr": 0.05, /* … */ },
      "fcff_dcf": {
        "ok": true,
        "enterprise_value": …,
        "equity_value": …,
        "value_per_share": …,
        "projected": [ { "year": 1, "revenue": …, "fcff": …, "pv_fcff": … } ]
      },
      "ev_ebitda": { "ok": true, "enterprise_value": …, "value_per_share": … }
    }
  ],
  "value_band": {
    "equity_value": { "low": …, "mid": …, "high": … },
    "per_share": { "low": …, "mid": …, "high": … },
    "shares_out": …
  },
  "sensitivity_wacc_g": [ { "wacc": …, "terminal_growth": …, "equity_value": … } ]
}
```

UI DCF 창은 `assumptions_seed.presets.base`를 폼 초기값으로 사용.

### 3.11 `levels` (단계 공개) ★ 제품 표면

정본: [`LEVELS_OUTPUT.md`](./LEVELS_OUTPUT.md)

```jsonc
"levels": {
  "beginner": { "sections": [/* 규모·마진·ROE·유동·부채 */], "checklist_ko": […] },
  "investor": { "includes_level": "beginner", "desk_ref": true, /* +FCF·ND/EBITDA·peer·시세·DCF밴드 */ },
  "ma": { "includes_level": "investor", "slots": { "ebitda_normalized": { "available": false }, … } }
}
```

UI 탭 = `levels.beginner | investor | ma`. 원시 `ratios` 전체를 한 화면에 뿌리지 않는다.

### 3.12 `narrative`

```jsonc
{
  "bullets_ko": ["산업 키트: 일반기계.", "…"],
  "by_lens": {
    "growth": ["매출 YoY +4.3%…"],
    "leverage": ["ND/EBITDA 1.96x…"]
  }
}
```

### 3.13 `summary` (유니버스/리스트)

```jsonc
{
  "ticker": "CAT",
  "name": "CATERPILLAR INC",
  "year": 2025,
  "parse_status": "verified",
  "kit_id": "machinery",
  "headline_ko": "…",
  "scorecard_status": { "growth": "watch", "leverage": "ok", /* … */ },
  "key": {
    "opm": 16.5,
    "fcf": 8918e6,
    "nd_ebitda": 1.96,
    "per": 44.9
  }
}
```

`build_universe.py`는 company 전체가 아니라 `summary` 배열만 써도 됨.

### 3.14 `provenance` (감사)

```jsonc
{
  "REVENUE": { "match": "id:us-gaap_Revenues", "account_nm": "Revenues" },
  "COGS": { "match": "id:us-gaap_CostOfRevenue", "reason": null }
}
```

UI 기본 숨김. “출처” 토글에서만.

---

## 4. 공통 셀 타입

```ts
type Measure = {
  value: number | null
  unit: "pct" | "x" | "currency" | "shares"
  reason?: string | null
  label_ko?: string
  trend_3y?: (number | null)[]  // older → newer
  yoy?: number | null
  yoy_unit?: "pct" | "pp" | "Δ"
}

type ScoreStatus = "ok" | "watch" | "risk" | "n/a"
```

---

## 5. API / 파일 배치 (배포 계약)

| 산출물 | 경로/엔드포인트 (제안) | 내용 |
|--------|------------------------|------|
| 기업 풀 | `GET /api/kfa/:ticker` 또는 `public/data/kfa/{ticker}.json` | `dart-company-v2` |
| 유니버스 | `public/data/dart_universe_v1.json` → 이후 `kfa_universe_v2.json` | `summary[]` |
| 라이브 | Worker: DART/SEC 프록시 → 엔진(또는 사전배치) → v2 JSON | 캐시 KV |

**UI 렌더 우선순위**
1. `quality.parse_status`
2. `desk` (scorecard + trend + bridges + notes)
3. `market` / `valuation_snapshot`
4. 탭: `views.*` → 상세 `ratios` / `valuation.scenarios`

---

## 6. 구현 단계 (엔진)

| Step | 작업 | 하위호환 |
|------|------|----------|
| A | `fundamental_pack` → 응답 키 `desk` 별칭 추가 | v1 유지 |
| B | `statements.series` 명시 필드 추가 | accounts 유지 |
| C | `ma_metrics` → `bridges` 복사본 추가 | 중복 일시 허용 |
| D | `views` + `ratios.index_by_level` | |
| E | `schema_version: dart-company-v2` 전환, v1 키 deprecate 목록 | Claude UI 동시 패치 |
| F | 5년 series (`trend_5y`) SEC 멀티연도 | optional |

---

## 7. 넣지 않는 것 (의도적)

- 투자의견 / 목표가 / Buy·Sell
- LLM 생성 문장
- 시세를 “적정가”로 단정하는 필드
- GPU·토큰 메타

---

## 8. CAT 예시 — UI가 실제로 읽는 최소 경로

```
quality.parse_status = verified
desk.headline_ko
desk.scorecard[]          → 5개 신호등
desk.trend_table          → 3년 one-pager
desk.cash_bridge
desk.leverage_bridge
desk.market_snapshot      → PER, EV/EBITDA
desk.valuation_snapshot   → DCF mid vs market %
desk.desk_notes_ko        → 금융자회사 착시 등
```

이 경로만으로 금융 란 1차 화면 완성. 나머지는 drill-down.

---

## 9. 다음 액션

1. **합의:** 이 v2 골격 OK 여부 (특히 `desk` 단일 진입점).  
2. **엔진:** Step A–C 구현 (별칭·series·bridges).  
3. **Claude:** `desk` 바인딩 UI (Cursor는 UI 파일 수정 안 함).
