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
- `docs/UI_HANDOFF.md` — UI 연동 계약

> 배포 패키지에는 아직 `docs/VIEWS_AND_MODELS.md`, `docs/DCF_REALISM.md`,
> `sec_facts.py`, `dart_facts.py`, `fetch_live.py`가 포함되지 않았습니다.
> 이 문서가 그 파일들이 존재한다고 말하는 것은 배포 상태와 맞지 않습니다.
> `derived_cards.py`와 `enrich_snapshot.py`는 외부 API 없이 정규화된 pack 또는
> 기존 JSON 스냅샷을 계산할 수 있지만, 누락된 원천 계정은 추정하지 않습니다.

## 코드
- `dart_kfa/view_presets.py` — 카드·모델 필터
- `dart_kfa/accounting_pack.py` — 기본 회계·유동성 스켈레톤
- `dart_kfa/model_contracts.py` — 모델 기본 가정·스텁
- `dart_kfa/derived_cards.py` — 전문가 카드·9개 모델·기간정렬 게이트
- `enrich_snapshot.py` — 오프라인 JSON 보강 CLI

## 현재 데이터 상태
- 배포된 샘플은 `New for anti/public/data/kfa_005930_v1.json` 하나이며,
  원시 공시 facts와 D&A·세금·이자비용·NWC·시가총액·세그먼트를 모두 담고 있지 않습니다.
- 따라서 이 샘플에서 가능한 카드만 계산하고 나머지는 `null + reason`으로 남깁니다.
- 새 JSON은 반드시 `New for anti/public/data/kfa_<code>_v1.json` 아래에 둡니다.
  저장소 루트 `public/data/`는 Cloudflare asset root가 아닙니다.

```bash
cd scripts/dart
python3 -m unittest discover -s tests -v
python3 enrich_snapshot.py ../../New\ for\ anti/public/data/kfa_005930_v1.json --output /tmp/kfa_005930_enriched.json
```
