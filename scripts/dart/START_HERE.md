# KFA Engine — START HERE

## 범위
- 경로: `scripts/dart/` 만
- UI (`app.js` 등) 수정 금지

## 지금 고정된 것
1. **4모드**: `basic` (기본) · `investor` · `pe` · `deal`
2. **공통 기본**: 매출·영업이익·순이익·CFO·FCF·현금·순차입·유동성·1년 만기·이자보상·CCC
3. **모델 (Basic 제외, 각 최대 3)**
   - Investor: `oe_hurdle` · `reverse_dcf` · `oe_yield`
   - PE: `delever_path` · `coverage_capacity` · `fcf_yield_entry`
   - Deal: `fcff_dcf` · `trading_comps` · `sotp_or_ev_bridge`
4. **DCF 현실화**: g 상한 3%, 시드=공시, bear/bull 델타 명시, WACC 민감도 필수, 목표가 없음

## 문서
- `docs/VIEWS_AND_MODELS.md` — 모드·카드·모델
- `docs/DCF_REALISM.md` — FCFF 규칙
- `docs/UI_HANDOFF.md` — UI 연동 계약

## 코드
- `dart_kfa/view_presets.py` — 카드·모델 필터
- `dart_kfa/accounting_pack.py` — 기본 회계·유동성 스켈레톤
- `dart_kfa/model_contracts.py` — 모델 기본 가정·스텁
- `dart_kfa/sec_facts.py` — SEC companyfacts → accounting_pack
- `dart_kfa/dart_facts.py` — OpenDART → accounting_pack (DART_API_KEY env)
- `fetch_live.py` — CLI

## Basic 채움 상태
- SEC + OpenDART: P&L, CFO, Capex, FCF(+series), 현금, 순차입, 1년 만기, 유동성 커버리지, 유동비율, CCC
- Sample UI JSON: `public/data/kfa_aapl_v1.json`, `public/data/kfa_005930_v1.json`

```bash
cd scripts/dart
python3 -m unittest discover -s tests -v
python3 fetch_live.py --ticker AAPL
DART_API_KEY=… python3 fetch_live.py --kr --stock 005930
```
