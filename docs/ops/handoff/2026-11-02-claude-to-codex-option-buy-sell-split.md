# 2026-11-02 Claude → Codex: 옵션 외국인 매수·매도 분리 실험

#797 shadow 엔진 리뷰 후속. 사용자 요청: 콜·풋 외국인 수급을 순매수 하나로 합치지 말고
**콜 매수 / 콜 매도 / 풋 매수 / 풋 매도**로 나눠서 다음 거래일 방향에 정보가 있는지 확인.

## 왜

현재 v1·shadow 옵션 입력은 `foreign.net_krw / market_total.buy_krw` 하나뿐이다.
매수 810억·매도 840억인 날과 매수 10억·매도 39억인 날이 같은 −29억이 된다.
거래 규모와 매수·매도 각각의 쏠림은 한 번도 시험하지 않았다.

원자료는 이미 구분돼 있다 (Claude 확인, `public/data/derivatives_board_v1.json`
→ `kr.investor_nets.detailed_15007.products`):

- `options_call`, `options_put`: 2019-01-02~2026-10-30, 1,921일, 전부 `observed`
- `foreign.{buy_krw, sell_krw, net_krw}` 1,921/1,921일 존재, `buy − sell = net` 불일치 0
- 외국인 매수 비중(외국인 매수/시장 매수) 중앙값 콜 70%, 풋 72% (범위 51~94%)
- `futures` 는 3일뿐 → 이번 실험에서 제외
- 기관·개인 없음(외국인 + 시장 전체만), 신규/청산 구분 없음 — 새 수집 금지

## 사전 고정 변형 (이것만 돌리고 추가 탐색 금지)

공통: 비율의 분모는 같은 날 `market_total.buy_krw`. 각 시계열에서 직전 60거래일
순위(`rank60`, 기존 정의)와 5일 평균(`mean5`)을 만든다.

| ID | 옵션 입력 | 개수 |
|---|---|---:|
| N0 | 현행 순매수 (call/put net 의 rank60, mean5) — 재현 기준 | 4 |
| S1 | 콜 매수·콜 매도·풋 매수·풋 매도 비중의 rank60, mean5 (순매수 대체) | 8 |
| S2 | N0 + 시장 전체 콜·풋 매수대금 자체의 rank60 (거래 활발도) | 6 |

각 변형을 (a) 옵션만, (b) 기존 shadow 가격 6개 + 옵션 으로 돌린다. 총 6개 모델.

## 평가 규칙 (#797 과 동일하게)

- `research_option_dynamics.py` 의 시간순 base/calibration/evaluation 분리, purge,
  분기 확장 학습, 단조(기울기 ≥ 0) sigmoid 보정, C=1, 임계값 0.5 를 그대로 재사용.
- `ReviewedCalendar`(6개 휴장 보정) 사용. 평가 날짜는 6개 모델 공통 날짜로 통일
  (#797 기준 1,178일 근처가 나와야 함; 다르면 이유 기록).
- 비교 기준 두 개: 최근 보정 구간 상승 비율, 그리고 N0(b).
- 지표: 적중률, Brier, log loss, 5거래일 블록 부트스트랩 95% 구간(seed 42, 1,000회),
  6개 비교에 Holm 보정, 왕복 0/5/10bps 거래당 평균.
- 보정 기울기가 0으로 떨어지는 분기 수를 변형별로 보고 (지금 shadow 의 핵심 문제).
- 결과가 좋든 나쁘든 6개 전부 보고. 결과를 보고 변수를 바꾸지 말 것.

## 산출물

- 코드: `New for anti/scripts/market_microstructure/research_option_buy_sell_split.py`
  + `tests/` 회귀검사 (분모·rank 인과 순서, buy−sell=net 항등식, 공통 날짜)
- 결과: `data/manifests/option_buy_sell_split_20261102.json` (압축 요약)
  + 같은 이름 `.md` 한국어 보고서 (표 하나에 6개 모델 + 두 기준)
- 인수인계: `docs/ops/handoff/<날짜>-codex-option-buy-sell-split.md`

## 하지 말 것

- v1 모델(`models/option_direction_v1_20261030.json`)·shadow 아티팩트·기존 예측 파일 수정 금지.
  shadow 엔진의 `implementation_sha256` 대상 5개 파일도 건드리지 말 것 (수정하면 예측이 멈춤).
  공통 함수가 필요하면 import 만 하거나 새 파일에 둔다.
- UI·workflow·`public/data` 수정 금지 (UI 는 Claude 가 B안 카드로 붙임).
- 새 KRX 조회, private chain 재수집 금지.
- 유의미해 보여도 모델 승격·새 shadow 아티팩트 생성은 하지 말고 보고만.

## 브랜치·PR

최신 main 에서 `codex/option-buy-sell-split-<날짜>`. 독립 PR, main 대상.
병합·배포는 사용자 확정 후 Claude.
