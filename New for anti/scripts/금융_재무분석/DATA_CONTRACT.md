# portfolio_analysis_v1 — UI 데이터 계약

경로: `public/data/portfolio_analysis_v1.json`

UI는 숫자 객체와 함께 **`ui_copy_ko`** / **`ui_copy_en`** 을 우선 렌더하세요.  
로케일만 바꿔 같은 카드 구조를 쓰면 됩니다 (`_ko` ↔ `_en`).  
재무 용어 없이도 읽히도록 문장·카드·비유를 넣어 두었습니다.

## Top-level

| 필드 | 설명 |
|------|------|
| `ui_copy_ko` | 화면용 친절한 한글 (headline, metric_cards, moves_*) |
| `ui_copy_en` | 동일 구조의 영어 (`headline_en`, `metric_cards` title/value/plain/analogy `_en`, …) |
| `risk_profile_id` | `conservative` \| `balanced` \| `aggressive` |
| `profile_check` | 성향 한도 위반 (`breaches_ko` / `breaches_en`) |
| `structure.clusters` | 함께 움직이는 묶음 (`label_ko` / `label_en`) |
| `structure.currency_exposure` | 원화 vs 외화 비중 |
| `stress` | 과거 급락 구간에 현재 비중 대입 (`label_ko` / `label_en`) |
| `advice` | HRP 조절 방향 (`no_expected_return: true`, `notes_ko` / `notes_en`) |
| `disclaimer_ko` / `disclaimer_en` | 고지 |

## ui_copy_ko / ui_copy_en (화면 권장)

스키마는 평행합니다. 한글은 `_ko`, 영어는 `_en` 접미사.

- `headline_ko` / `headline_en` — 한 줄 요약
- `profile.label_*` / `profile.blurb_*` — 성향 라벨·한 줄 설명
- `how_to_read_ko` / `how_to_read_en` — “이 숫자 보는 법”
- `metric_cards[]` — 출렁임 / 샤프 / VaR / 1년 성적 + `plain_*` + `analogy_*`
- `risk_contribution_plain_ko` / `_en`
- `clusters_plain_*` / `currency_plain_*` / `stress_plain_*`
- `moves_up_*` / `moves_down_*` — 비중 조절 문장
- `footer_*` / `rebalance_note_*`

## 자동완성

```bash
python3 run_pipeline.py --suggest "삼성전"
```

## 성향

`instruments/risk_profiles.json` — 현금 밴드, 주식 상한, 단일종목, 레버리지, 10일 VaR 예산.  
라벨: `label_ko` / `label_en`, `blurb_ko` / `blurb_en`.  
**목표 수익률 입력 없음** (기대수익 가정 안 씀).
