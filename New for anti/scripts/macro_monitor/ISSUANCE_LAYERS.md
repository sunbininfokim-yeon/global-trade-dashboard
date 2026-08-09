# 미 국채 발행 · 레이어 스택 (통시 × 정태)

선빈: *통시적·정태적 관점을 잘 알 수 있도록 레이어를 쌓는다.*

정본 JSON: USA `qra_issuance.issuance_layers`  
모듈: `macro_monitor/issuance_layers.py`  
UI: Claude — **밴드 탭 + 기본 레이어 A1**. 기자 기사 레이아웃 복제 금지.

```text
┌──────────────────────────────────────────────────────────────┐
│ L0  칩  당기 순발행 $B · 스탠스 플래그          【정태 요약】│
├────────────────────────  A · 정태 해부  ─────────────────────┤
│ A1  3-way 비교  전분실적 | 직전예측 | 당기     ★ 기본 오픈   │
│ A2  Bill | Coupon 스택                         구성 한 장    │
│ A3  만기별 바+표                               표 = 정밀     │
│ A4  Sources & Uses                             왜 그 숫자?   │
├────────────────────────  B · 통시  ──────────────────────────┤
│ B1  분기 순발행 궤적 (history_net_borrowing)   세로 시간축   │
│ B2  동일 분기 재추정 (5월→8월 공시)            수정 폭       │
│ B3  DTS 일별 순발행 · TGA 라인                 발표 사이 실적│
├────────────────────────  C · 좌표  ──────────────────────────┤
│ C1  SOMA 보유 스택                             누가 들고 있나│
│ C2  순유동성 · ON RRP · MTS 적자               남는 유동성   │
└──────────────────────────────────────────────────────────────┘
```

## 왜 이 순서인가

| 축 | 질문 | 레이어 |
|----|------|--------|
| **정태** | “이번 공시, 얼마? 뭐로? 왜?” | A1 → A2 → A3 → A4 |
| **통시** | “평소 대비? 고쳤나? 실제로?” | B1 → B2 → B3 |
| **좌표** | “연준·은행·재정 옆에서는?” | C1 → C2 |

기사가 한 번에 쏟는 것(문안 + 빌 순발행 + 만기 표 + FY 합)을 **밴드 세 겹**으로 나눈다.  
한 화면에 전부 올리면 통시도 정태도 둘 다 죽는다.

## UI 계약

| 필드 | 의미 |
|------|------|
| `issuance_layers.bands[]` | hero / static_dissect / diachronic / context |
| `issuance_layers.layers[]` | id · axis · view · bind · default_open · why_ko |
| `issuance_layers.ui.default_layer_id` | `A1_compare` |
| `issuance_layers.read_path_ko` | 권장 읽기 순서 (카피/툴팁용) |
| `ui.layers_view` | `"issuance_layers"` |
| `ui.click_view` | 유지: `compare_bar_table` (= A1) |

`bind.fields` → 같은 지표 객체 필드  
`bind.sibling_series` → 같은 국가 pack의 다른 지표 id로 스크롤/딥링크

## 하지 말 것

- 기자 UI 표 전체 베끼기  
- FY YTD·3-3-3 해석을 A 밴드에 섞기 (설명 패널·뉴스)  
- A3/A4/B를 기본 오픈 (정보 과부하)
