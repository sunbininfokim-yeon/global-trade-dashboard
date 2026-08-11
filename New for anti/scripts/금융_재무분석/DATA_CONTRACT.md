# portfolio_analysis_v1 — UI 데이터 계약

경로: `public/data/portfolio_analysis_v1.json`

UI는 숫자 객체와 함께 카피 블록을 우선 렌더하세요.  
모드: **`basic`** (`ui_copy_basic_ko` / `ui_copy_basic_en`) vs **`expert`** (`ui_copy_ko` / `ui_copy_en`).  
로케일만 바꿔 같은 카드 구조를 쓰면 됩니다 (`_ko` ↔ `_en`).

## Top-level

| 필드 | 설명 |
|------|------|
| `ui_copy_basic_ko` | basic 모드 한글 — 사무/실무 표현 (VaR·샤프를 카드 제목에 쓰지 않음) |
| `ui_copy_basic_en` | basic 모드 영어 (동일 구조) |
| `ui_copy_ko` | expert 모드 한글 (headline, metric_cards, moves_*) |
| `ui_copy_en` | expert 모드 영어 (`headline_en`, `metric_cards` title/value/plain/analogy `_en`, …) |
| `risk_profile_id` | `conservative` \| `balanced` \| `aggressive` |
| `risk_profile_meta` | 선택 성향 전체 객체 (`cash_min`/`cash_max`, `var_10d_budget`, `cash_footnote_*`, `why_cash_band_*` 포함) |
| `risk_profile_footnotes` | 호버/툴팁용 요약 (`cash_footnote_ko`/`en`, `why_cash_band_ko`/`en`, 현금 밴드·VaR 예산) |
| `profile_check` | 성향 한도 위반 (`breaches_ko` / `breaches_en`) |
| `structure.clusters` | 함께 움직이는 묶음 (`label_ko` / `label_en`) |
| `structure.currency_exposure` | 원화 vs 외화 비중 |
| `stress` | 과거 급락 구간에 현재 비중 대입 (`label_ko` / `label_en`) |
| `advice` | HRP 조절 방향 (`no_expected_return: true`, `notes_ko` / `notes_en`) |
| `disclaimer_ko` / `disclaimer_en` | 고지 |
| `size_guide` | 개인 규모 구간 휴리스틱 (`aum_krw`, `bucket`, `names_min`/`max`, `prefer_etf`, `vs_actual`) — MPT 종목수 공식 아님 |
| `positions_truncated_ko` / `positions_truncated_en` | 상위 `MAX_NAMES`(기본 20) 절단 경고 문구 (없으면 null) |
| `input_normalize` | `max_names`, `aum_krw`, `residual_cash_added`, `truncated_positions[]` |

## 입력 → 정규화 (엔진)

포트폴리오 JSON 선택 필드:

| 필드 | 설명 |
|------|------|
| `total_value` 또는 `aum_krw` | 선택. 비어 있거나 0이면 Σ\|position.value\| |
| 합 < 총액 | 잔여 → 원화 현금 (`원화` / `cash:krw`) merge |
| 합 > 총액 | 파이프라인 에러 (silent drop 없음) |

처리 순서: 잔여 현금 → `MAX_NAMES=20` 절단 (`portfolio_lab/normalize.py`).  
채권·금 등 비주식 라인도 20캡·공분산에 포함.

### size_guide 스키마

```json
{
  "aum_krw": 50000000,
  "bucket": "standard",
  "label_ko": "확대",
  "label_en": "Standard",
  "names_min": 8,
  "names_max": 20,
  "prefer_etf": false,
  "footnote_ko": "규모 구간 휴리스틱. MPT 종목수 공식 아님.",
  "vs_actual": { "n_names": 12, "status": "ok" }
}
```

`vs_actual.status`: `ok` \| `too_many` \| `too_few`.

## basic vs expert

| 모드 | 키 | 톤 |
|------|-----|-----|
| **basic** | `ui_copy_basic_ko` / `ui_copy_basic_en` | 사무/실무 문구. 카드 제목 예: 예상 등락 폭, 단기 손실 가능 규모, 위험 대비 수익 효율 (과거), 현금·대기자금. 현금 조언은 **성향 `cash_min`/`cash_max` 밴드** (예: conservative 25–45%). HRP가 현금을 크게 잡아도 성향 밴드를 공식 목표로 씀. `glossary_note_*`로 expert 지표 안내. |
| **expert** | `ui_copy_ko` / `ui_copy_en` | 변동성·샤프·VaR 등 지표명을 제목에 노출. |

## ui_copy_basic_* (basic 화면 권장)

- `mode`: `"basic"`
- `headline_ko` / `headline_en` — 성향 → 문제 → 조치 스토리
- `profile` + `cash_band_*` — 성향 라벨·현금 권장 구간
- `metric_cards[]` — 등락 폭 / 단기 손실 규모 / 수익 효율 / 현금·대기자금 / 1년 수익 (+ `plain_*` + `analogy_*`)
- `risk_contribution_title_*` — 계좌 흔들림 집중도 / Account-swing concentration
- `moves_title_*` — 비중 조정 제안 / Suggested weight moves
- `glossary_note_ko` / `glossary_note_en` — VaR·Sharpe는 expert 모드 안내
- `size_note_ko` / `size_note_en` — 규모 구간·20종 절단 요약 (없을 수 있음)
- 그 외 expert와 평행: `how_to_read_*`, `clusters_plain_*`, `moves_up_*` / `moves_down_*`, `footer_*`, `rebalance_note_*`

## ui_copy_ko / ui_copy_en (expert 화면 권장)

스키마는 평행합니다. 한글은 `_ko`, 영어는 `_en` 접미사.

- `headline_ko` / `headline_en` — 한 줄 요약
- `profile.label_*` / `profile.blurb_*` — 성향 라벨·한 줄 설명
- `profile.cash_min` / `profile.cash_max` — 성향 현금 밴드
- `profile.why_cash_band_*` — 밴드 근거 한 줄 (툴팁 요약)
- `profile.cash_footnote_*` — 보수/일반/공격 호버·클릭 각주 (제품 휴리스틱 · Kelly/CAPM 아님 · HRP와 밴드 역할 구분)
- `how_to_read_ko` / `how_to_read_en` — “이 숫자 보는 법”
- `metric_cards[]` — 출렁임 / 샤프 / VaR / 1년 성적 + `plain_*` + `analogy_*`
- `risk_contribution_plain_ko` / `_en`
- `clusters_plain_*` / `currency_plain_*` / `stress_plain_*`
- `moves_up_*` / `moves_down_*` — 비중 조절 문장
- `footer_*` / `rebalance_note_*`
- `size_note_ko` / `size_note_en` — 규모 구간·절단 요약 (optional one-liner; 없으면 null)

## 자동완성

```bash
python3 run_pipeline.py --suggest "삼성전"
```

## 성향

`instruments/risk_profiles.json` — 현금 밴드, 주식 상한, 단일종목, 레버리지, 10일 VaR 예산.  
라벨: `label_ko` / `label_en`, `blurb_ko` / `blurb_en`.  
각주: `cash_footnote_ko`/`en`, `why_cash_band_ko`/`en` (성향별).  
최상위 `methodology_note_ko`/`en` — 밴드는 정책 휴리스틱이며 최적 현금 공식이 아님.  

**Claude UI (보수/일반/공격 호버):**  
우선 `ui_copy_ko.profile.cash_footnote_ko` / `ui_copy_en.profile.cash_footnote_en`  
폴백 `risk_profile_footnotes.cash_footnote_ko` / `_en` 또는 `risk_profile_meta` 동일 키.  
한 줄 요약은 `why_cash_band_*`.  

**목표 수익률 입력 없음** (기대수익 가정 안 씀).
