# Cursor → Grok 핸드오프 — 호가 및 유동성 / Market Microstructure
## 나
- 선빈 (Researcher)
- 레포: sunbininfokim-yeon/global-trade-dashboard
- 로컬: Documents/New for anti-dart
- 브랜치: cursor/macro-monitor-fix
- PR: https://github.com/sunbininfokim-yeon/global-trade-dashboard/pull/36
- Cursor 잔여량 소진 → Grok로 데이터/엔진 계속
## 제품 (3탭, KO≠EN 직역 금지)
메뉴: ko 「호가 및 유동성」 / en 「Market Micro-metrics」
1. 수급 불균형 모니터링 / Distortion & Squeeze
2. 가격대별 체결 분포 / Volume Profile
3. 해외-국내 선행 지표 / Global Spillover Effect
## YouTube (원 요청에 준 것 — 먼저 시청/요약)
1. https://www.youtube.com/watch?v=qgGh6dpe5H4
2. https://www.youtube.com/watch?v=GC6lEduc8JY
3. https://www.youtube.com/watch?v=ZQAKPiQ-Zuk
4. https://www.youtube.com/watch?v=hd51V3Z0Vsk
5. https://www.youtube.com/watch?v=T6JMqFf_HiQ
6. https://www.youtube.com/live/0DPPQLdP5zk
축: 하닉 레버 ETF, 숏감마, 시총 쏠림, HK CSOP, 코스피 비중, (ELS/LP는 public 한계)
## PDF (Downloads — 그록에 재업로드)
- the ai casino is closing.pdf
- The AI Bubble s Canary Just Died.pdf
- The AI Trade s Moment Of Truth.pdf
- is korea the next china 2015.pdf
앵커: scripts/market_microstructure/config/paper_anchors.json
## 코드 루트 (여기만 수정 OK)
New for anti/scripts/market_microstructure/**
산출 JSON: New for anti/public/data/
  market_microstructure_v1.json
  ai_casino_brief_v1.json
  investor_price_levels_v1.json
  us_kr_transmission_v1.json
  kospi_concentration_history_v1.json
  alert_levels_v1.json
  derivatives_board_v1.json
  validation_backtest_v1.json
문서 순서: README → DATA_SOURCES → GOBUS_AND_GLOBAL_STACK → GROK_HANDOFF.md
→ formulas.py → engine.py → letf_universe.json → 최신 market_microstructure_v1.json
## 수정 금지
app.js, style.css, index.html, data.js, shipping.js, _worker.js, wrangler, workflows
## 재빌드
cd New for anti/scripts/market_microstructure
python build_market_microstructure.py --live --source auto --fx 1400
## 공식
TR = AUM*(L²-L)*R ; IR% = |TR|/ADV*100
letf_turnover = LETF_TV / spot_ADV (= 현물 대비 회전율)
lev_exposure = Σ(AUM×|L|)/free_float_mcap
HK/US/crypto는 KR cash 회전율 식에 합산 금지. 단 UI·모니터에는 1급으로 포괄.
헷지 경로: 해외 레버/옵션 → 스왑 상대(한국 기관) 헷지 → 국내 현물/선물/국내 LETF
## 주요 필드
stocks[].letf_turnover_ratio, products, products_hk (7709 메인, 7708 아님)
market_letf_derivatives_ratios, letf_category_share.by_direction (gobus_inverse_2x)
global_leverage_stack (US: SOXL SOXS KORU TECL TECS TQQQ SQQQ)
us_kr_transmission: why_ko, evidence_us
investor_price_levels: 가격 Y, 매수+ 매도- (틱 매집 아님)
deposit_credit: 예탁·신용; 미수/반대매매=missing (가짜 금지)
## 최근 커밋
73d4205 곱버스+글로벌 레버 spillover
4b25d8d dart KFA (별 트랙 — 재무, 이 메뉴와 섞지 말 것)
## 가짜 숫자 금지 / quality missing은 빈칸
다음 작업: 1순위 진행 중 — by_direction(곱버스) + US 인버스 스택(SOXS/TECS/SQQQ) + GOBUS_AND_GLOBAL_STACK.md + paper_anchors v2. 라이브 재빌드 대기.
