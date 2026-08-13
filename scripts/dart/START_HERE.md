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
- `docs/VIEWS_AND_MODELS.md` — 모드·카드·모델 계약
- `docs/DCF_REALISM.md` — FCFF 규칙과 산업 적용 한계
- `docs/UI_HANDOFF.md` — UI 연동 계약

> `derived_cards.py`와 `enrich_snapshot.py`는 외부 API 없이 정규화된 pack 또는
> 기존 JSON 스냅샷을 계산할 수 있지만, 누락된 원천 계정은 추정하지 않습니다.
> `sec_facts.py`, `fetch_live.py`는 아직 없음. `dart_facts.py`는 2026-08-13부터
> 있음 (아래 소유권 절 참고) — `DART_API_KEY` 환경변수가 없으면 조용히
> 빈 facts를 반환하고 네트워크 호출을 하지 않습니다.

## 소유권 / 핸드오프 (2026-08-13)

- `dart_facts.py` (OpenDART 어댑터)는 **임시로 Claude가 재개**했습니다.
  UI/배포 소유권과는 별개이며, 이 엔진의 정식 소유자(Grok/Cursor/사용자)가
  정해지면 언제든 그대로 넘길 수 있게 짰습니다:
  - `dart_kfa/__init__.py`가 기대하는 심볼(`fetch_accounting_pack_kr`) 계약만
    지키면 내부 구현은 자유롭게 바꿔도 됩니다.
  - API 키는 코드에 없습니다 — 실행 전 `export DART_API_KEY=...`.
  - UI(`New for anti/app.js`)나 다른 엔진 파일(`accounting_pack.py`,
    `derived_cards.py` 등 이미 있던 파일)은 건드리지 않았습니다.
- 다음 사람이 이어받을 때 볼 것: `dart_kfa/dart_facts.py` 상단 docstring +
  `XBRL_TAGS` 매핑 (아직 OpenDART 실제 계정과목명으로 검증 안 됨 — 추정치).

## 코드
- `dart_kfa/view_presets.py` — 카드·모델 필터
- `dart_kfa/accounting_pack.py` — 기본 회계·유동성 스켈레톤
- `dart_kfa/model_contracts.py` — 모델 기본 가정·계산 계약
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
