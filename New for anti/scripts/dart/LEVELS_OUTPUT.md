# Engine output: `levels` (단계 공개)

**이게 요청의 본체.**  
취준생 → 주식 투자 → M&A 사냥꾼 순으로, **쉬운 지표에서 전문 지표로** 엔진 JSON을 나눈다.

- 스키마 키 이름: **`levels`** (`views` 아님)
- UI는 탭/토글로 `beginner | investor | ma` 중 하나만 펼친다
- 원천 숫자(`statements` / `ratios` / `bridges`)는 공유하고, **levels는 “무엇을 보여줄지” 인덱스 + 요약 셀**

관련 전체 골격: [`OUTPUT_SCHEMA.md`](./OUTPUT_SCHEMA.md)  
여기 문서만으로 Claude UI / 엔진 구현이 가능해야 한다.

---

## 1. 왜 levels인가

지금은 지표가 **한 덩어리**라 단순해 보인다.

| 문제 | levels로 해결 |
|------|----------------|
| 유동비율·ROE·FCF·ND/EBITDA·DCF가 같은 높이 | 탭별로 노출 범위 제한 |
| L3(사업부·정상화·우발) 약함 | `ma`에 슬롯 + `available:false`로 빈자리 명시 |
| 3년만 있음 | 각 레벨 `trend`에 3년 기본, `ma`/`investor`에 5년 슬롯 예약 |

**투자의견 아님.** “이 단계에서 볼 체크리스트”다.

---

## 2. 최상위 위치

```jsonc
{
  "schema_version": "dart-company-v2",
  "issuer": { },
  "period": { },
  "quality": { },
  "statements": { },
  "ratios": { "metrics": { } },
  "bridges": { },
  "industry": { },
  "desk": { },              // 현업 원페이저 (investor의 압축판으로도 씀)
  "market": { },
  "valuation": { },

  "levels": {
    "beginner": { /* §3 */ },
    "investor": { /* §4 */ },
    "ma": { /* §5 */ }
  }
}
```

UI 기본 탭 추천: **`investor`** (서비스 포지션이 금융 분석).  
교육 모드만 `beginner`, 딜/실사 모드만 `ma`.

---

## 3. 공통 셀 형태

모든 레벨이 같은 블록 모양을 쓴다.

```jsonc
{
  "id": "beginner",
  "label_ko": "기초",
  "label_en": "Beginner",
  "audience_ko": "취준생 · 재무제표 입문",
  "goal_ko": "한 해 숫자와 기본 비율로 ‘건강한가’를 말한다",
  "sections": [
    {
      "id": "size",
      "title_ko": "규모",
      "items": [
        {
          "metric_id": "REVENUE",          // statements 또는 ratios 키
          "source": "statements.accounts", // statements.accounts | ratios.metrics | bridges.* | market | valuation | computed
          "label_ko": "매출",
          "value": 67589000000,
          "unit": "currency",
          "trend_3y": [67060e6, 64809e6, 67589e6],
          "yoy": 4.29,
          "yoy_unit": "pct",
          "explain_ko": "회사가 판 금액. 늘었는지부터 본다.",
          "reason": null
        }
      ]
    }
  ],
  "checklist_ko": ["매출이 늘었나?", "이익이 났나?", "빚이 자본보다 과도한가?"],
  "hidden_until_next_ko": ["FCF", "Net Debt/EBITDA", "PER", "DCF"],  // 다음 레벨에서 연다
  "status_rollup": "ok|watch|risk|n/a|mixed"   // optional, desk scorecard 요약
}
```

규칙:
- `value`/`trend`는 **엔진이 resolve한 스냅샷** (UI가 ratios를 다시 조인하지 않아도 되게)
- `metric_id`로 원천 추적 가능
- 없으면 `value: null`, `reason: "missing:…"`, 섹션은 유지 (자리 보존)

---

## 4. `levels.beginner` — 취준 / 입문

**질문:** 이 회사 숫자 읽고 면접에서 말할 수 있나?

### 섹션 · 지표 (고정 리스트)

| section | metric_id | source | 설명 한 줄 |
|---------|-----------|--------|------------|
| size | REVENUE | statements | 매출 |
| size | OPERATING_INCOME | statements | 영업이익 |
| size | NET_INCOME | statements | 순이익 |
| profitability | operating_margin | ratios | 영업이익률 |
| profitability | net_margin | ratios | 순이익률 |
| returns | roe | ratios | ROE |
| returns | roa | ratios | ROA |
| solvency | current_ratio | ratios | 유동비율 |
| solvency | debt_ratio | ratios | 부채비율 |
| trend | (위 핵심 3~4개의 trend_3y만) | — | 3년 막대/표 |

**넣지 않음:** FCF, ND/EBITDA, PER, DCF, peer, 리스·계약부채, 사업부.

```jsonc
"beginner": {
  "id": "beginner",
  "label_ko": "기초",
  "audience_ko": "취준생 · 재무 입문",
  "goal_ko": "규모·마진·ROE·유동성·부채비율로 기본 체력을 말한다",
  "sections": [ /* 위 표 */ ],
  "checklist_ko": [
    "매출·영업이익·순이익이 흑자인가",
    "영업이익률이 업종 감으로 이상한가 (아직 peer 비교는 다음 단계)",
    "유동비율이 100% 전후인가",
    "부채비율이 급격히 악화됐는가 (3년)"
  ],
  "hidden_until_next_ko": [
    "FCF·이익의 질",
    "Net Debt/EBITDA",
    "업종 peer",
    "시세 배수·DCF"
  ]
}
```

---

## 5. `levels.investor` — 주식 투자 펀더멘탈

**질문:** 현금·레버리지·사이클·시장 기대까지 보고 판단 재료가 되나?

beginner **전부 포함(상속)** + 아래를 연다.

| section | metric_id | source | 설명 |
|---------|-----------|--------|------|
| cash | fcf | ratios/bridges | 잉여현금흐름 |
| cash | fcf_margin | bridges | FCF 마진 |
| cash | earnings_quality | ratios | CFO/NI |
| cash | CFO, CAPEX | statements | 현금 브리지 재료 |
| leverage | net_debt | bridges | 순차입(순현금) |
| leverage | net_debt_to_ebitda | bridges | **본지표** |
| leverage | debt_ratio | ratios | 보조 (착시 주의 노트) |
| quality_ops | inventory_turnover | ratios | 재고 (COGS 기준) |
| quality_ops | asset_turnover | ratios | 자산회전 |
| peer | peer.vs[] | industry | 한은 등 구조 비교 + caveat |
| market | per, pbr, ev_ebitda | market | 시세 있을 때만 |
| valuation | value_band.per_share | valuation | 가정 밴드 (목표가 아님) |
| desk | scorecard | desk | 5렌즈 신호등 (성장·수익·현금·레버리지·수익) |

```jsonc
"investor": {
  "id": "investor",
  "label_ko": "투자",
  "audience_ko": "주식 · 개인/준프로 펀더멘탈",
  "goal_ko": "현금전환·순차입 레버리지·3년 방향·시세 배수로 체력과 시장 기대를 분리한다",
  "includes_level": "beginner",
  "sections": [ /* beginner sections + cash/leverage/… */ ],
  "desk_ref": true,                    // UI가 desk 블록을 이 탭에 임베드
  "checklist_ko": [
    "FCF가 흑자이고 CFO가 순이익을 받치나",
    "ND/EBITDA가 관리 구간인가 (부채비율만 보지 말 것)",
    "마진·ROE가 피크에서 꺾이나 (3년)",
    "PER·EV/EBITDA가 말하는 기대와 DCF 가정 밴드가 얼마나 다른가"
  ],
  "hidden_until_next_ko": [
    "정상화 EBITDA",
    "사업부(ME&T vs Financial) 분리",
    "우발·보증·계약부채 조정",
    "NWC 실사 브리지"
  ],
  "trend": {
    "years": 3,
    "years_target": 5,                 // 엔진 미구현 시 null series
    "rows": ["REVENUE", "operating_margin", "fcf", "net_debt_to_ebitda"]
  }
}
```

---

## 6. `levels.ma` — M&A / 실사

**질문:** 인수·크레딧 실사에서 숫자 정의를 맞출 수 있나?

investor 포함 + **L3 슬롯** (없어도 키는 유지).

| section | metric_id | available 지금 | 설명 |
|---------|-----------|----------------|------|
| bridges | cash, leverage | ✅ | CFO−Capex, IB debt−cash−MSI |
| ebitda | ebitda_proxy | ✅ 대용 | OI+DA |
| ebitda | ebitda_normalized | ❌ 슬롯 | 일회성 제거 (수동/규칙 후속) |
| capital_structure | lease_to_liabilities | ✅ | 리스 |
| capital_structure | contract_liab_to_liabilities | △ | 조선 등 |
| capital_structure | net_debt_incl_lease | ✅ | |
| segment | ops_vs_finance | ❌ 슬롯 | CAT Financial 분리 |
| contingencies | guarantees_backlog_notes | ❌ 플래그/체크리스트 | 주석 유도 |
| returns | roic | △ | 계정 되면 |
| stress | valuation.scenarios bear/base/bull | ✅ | 가정 스트레스 |
| flags | industry.flags | ✅ | |

```jsonc
"ma": {
  "id": "ma",
  "label_ko": "M&A·실사",
  "audience_ko": "딜 · 크레딧 · 실사",
  "goal_ko": "정의된 Net Debt·EBITDA·FCF와 왜곡 요인을 체크리스트로 고정한다",
  "includes_level": "investor",
  "sections": [ /* … */ ],
  "slots": {
    "ebitda_normalized": {
      "available": false,
      "reason": "not_implemented",
      "placeholder_ko": "일회성·평가손익 조정 EBITDA (후속)"
    },
    "segment_ops_vs_finance": {
      "available": false,
      "reason": "not_implemented",
      "placeholder_ko": "제조·에너지 vs 금융자회사 분리 레버리지"
    },
    "nwc_bridge": {
      "available": false,
      "reason": "not_implemented",
      "placeholder_ko": "ΔNWC 실사 브리지"
    }
  },
  "checklist_ko": [
    "Net Debt 정의(이자부 − 현금 − 유가증권) 합의",
    "EBITDA 대용 vs 정상화 구분",
    "금융자회사·리스·계약부채 착시",
    "FCF와 수주/재고 사이클",
    "Bear 시나리오 DCF·배수"
  ],
  "trend": { "years": 3, "years_target": 5 }
}
```

L3가 약하다는 건 **버그가 아니라 `slots.available:false`로 드러내는 것**이 설계 의도.

---

## 7. UI가 읽는 방식 (Claude 계약)

```
[기초] [투자] [M&A]     ← levels 탭
   │       │       └─ ma.sections + slots(빈자리) + checklist
   │       └─ investor (+ desk 임베드) + market/valuation 요약
   └─ beginner.sections only
```

1. 탭 선택 → `levels[tab].sections`만 렌더  
2. `includes_level`이 있으면 부모 섹션을 **앞에 붙이거나** “기초 접기”  
3. `hidden_until_next_ko`는 다음 탭 CTA로 표시  
4. 차트는 `trend_3y` / 향후 `trend_5y`  
5. 원페이저 모드 = `desk` only (탭 없이)

---

## 8. 엔진 resolve 의사코드

```
build_levels(company):
  beginner = snap(BEGINNER_SPEC, company)
  investor = merge(beginner, snap(INVESTOR_SPEC, company), desk_ref=True)
  ma       = merge(investor, snap(MA_SPEC, company), slots=MA_SLOTS)
  return { beginner, investor, ma }
```

스펙은 `config/levels.spec.json`으로 고정 (지표 목록 하드코딩 금지 권장).

---

## 9. CAT 예시 (개념)

| 탭 | 사용자가 보는 것 |
|----|------------------|
| 기초 | 매출 67.6B, OPM 16.5%, ROE 42%, 유동 144%, 부채비율 362% + 3년 |
| 투자 | + FCF 8.9B, CFO/NI 1.32, ND/EBITDA 1.96, peer, PER~45, desk 신호등(성장 watch) |
| M&A | + 레버리지 브리지, 리스, **slots: 사업부 분리·정상화 EBITDA = 미구현**, Bear/Base/Bull |

---

## 10. 구현 순서

| Step | 내용 |
|------|------|
| 1 | `config/levels.spec.json` + `dart_kfa/levels.py` |
| 2 | `analyze` 결과에 `levels` 부착 (v1 병행) |
| 3 | `OUTPUT_SCHEMA.md`의 `views` 명칭을 `levels`로 통일 |
| 4 | Claude: 금융 란 탭 = `levels.*` |
| 5 | 후속: `trend_5y`, `slots` 채우기 (정상화·세그먼트) |

---

## 11. 한 줄 요약

**엔진 출력의 제품 표면은 `levels.{beginner,investor,ma}` 이고,**  
같은 회사 JSON을 난이도별로 잘라 보여주는 설계다.  
`desk`는 investor 탭의 압축 원페이저, `ma.slots`는 아직 없는 L3를 숨기지 않고 빈칸으로 남긴다.
