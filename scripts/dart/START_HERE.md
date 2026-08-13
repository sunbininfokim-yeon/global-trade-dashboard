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
- 2026-08-13: `XBRL_TAGS`는 실제 OpenDART 응답(삼성전자 00126380·SK하이닉스
  00164779, FY2024 CFS) 두 건으로 검증 완료. 엔드포인트도 존재하지 않는
  `/api/xbrlTaxonomy`에서 실제 경로 `/api/fnlttSinglAcntAll.json`로 교체.
  **알려진 한계**: 단기·장기차입금은 회사마다 태그가 다르고, 삼성전자
  단기차입금처럼 아예 표준 XBRL 코드가 없는 경우가 있음(`None`으로 정직하게
  남음). D&A는 두 회사 모두 별도 태그로 공시하지 않아 항상 비어 있음.
  이자비용은 IFRS `FinanceCosts`(순수 이자보다 넓은 범위)로 근사한 것이라
  `reason: approx:ifrs_finance_costs_not_pure_interest`가 붙음.
- 2026-08-13 (같은 날, 후속): `dart_facts.py` → UI가 읽는 `kfa_<code>_v1.json`
  까지 끝까지 연결하는 코드를 추가했습니다 (아래 "라이브 스냅샷 생성" 참고).
  이건 배선(wiring)이지 새 회사 데이터 발행이 아닙니다 — 이 세션엔
  `DART_API_KEY`가 없어서 실제 라이브 호출로 끝까지 검증하진 못했고, 대신
  OpenDART 응답 모양을 그대로 흉내 낸 fixture로 18개 유닛테스트를 붙였습니다
  (`tests/test_dart_facts.py`). 키를 가진 사람이 실행하면 바로 새 회사를
  추가할 수 있습니다.
- 다음 사람이 이어받을 때 볼 것: `dart_kfa/dart_facts.py` 상단 docstring +
  `XBRL_TAGS` 코멘트. 새 회사를 검증 없이 추가하면 이 두 회사에서 이미 드러난
  회사별 태그 불일치를 그대로 반복할 위험이 있음 — 최소 1개 회사로 실측 확인.

## 코드
- `dart_kfa/view_presets.py` — 카드·모델 필터
- `dart_kfa/accounting_pack.py` — 기본 회계·유동성 스켈레톤
- `dart_kfa/model_contracts.py` — 모델 기본 가정·계산 계약
- `dart_kfa/derived_cards.py` — 전문가 카드·9개 모델·기간정렬 게이트·
  `basic_cards_from_pack()`(pack → UI 카드 12개, 신규)
- `dart_kfa/dart_facts.py` — OpenDART 어댑터 (fetch + pack 매핑,
  `current_ratio`/`net_debt`/`debt_due_within_1y.components` 계산 포함)
- `dart_kfa/snapshot_builder.py` — `build_kfa_snapshot()`, 위 세 계층을
  묶어 UI가 바로 읽는 전체 JSON을 만드는 오케스트레이션 (신규)
- `enrich_snapshot.py` — 오프라인 JSON 보강 CLI (기존 스냅샷용)
- `fetch_kfa_snapshot.py` — 라이브 OpenDART 스냅샷 생성 CLI (신규)

## 라이브 스냅샷 생성 (신규 회사 추가)

```bash
export DART_API_KEY=...   # 코드에 없음, 실행 전 필수
cd scripts/dart
python3 fetch_kfa_snapshot.py <corp_code 8자리> <stock_code 6자리> "<한글명>" "<영문명>" --year 2025
# 기본 출력 경로: New for anti/public/data/kfa_<stock_code>_v1.json
```

**한계 (정직하게 문서화, 추정으로 메우지 않음):**
- **단일 회계연도만 가져옵니다.** 한 번의 OpenDART 호출 = 한 해치이므로
  `basic_cards`의 `series`가 1개 점뿐이고 `yoy`는 항상 `null`입니다. CAGR·
  이익의 질 추이 등 다년 비교가 필요한 전문가 카드는 자동으로
  `null + reason`이 됩니다 — 버그가 아니라 설계된 동작입니다. 여러 해를
  채우려면 `year`를 바꿔가며 여러 번 호출하고 series를 합치는 루프가
  필요한데, 아직 없습니다.
- `ccc_days`는 항상 `null` — DSO/DIO/DPO에 필요한 매출채권·재고·매입채무
  태그를 아직 fetch하지 않습니다.
- `debt_due_within_1y`는 `short_term_borrowings` 컴포넌트만 채워지고
  `value`(합계)는 항상 `null` — `current_portion_lt_debt`·`leases_current`
  태그가 없는 상태에서 부분합을 완전한 수치처럼 보여주지 않기 위함입니다.
- `net_debt`는 `marketable_securities`를 빼지 않습니다 (해당 태그 미fetch) —
  정의 문구에 명시되어 있습니다.

## 현재 데이터 상태
- 배포된 샘플은 `New for anti/public/data/kfa_005930_v1.json` 하나이며,
  원시 공시 facts와 D&A·세금·이자비용·NWC·시가총액·세그먼트를 모두 담고 있지 않습니다.
  이 샘플은 위 다년 계산(revenue 3개년 series, net_debt/current_ratio/ccc_days
  값 등)이 이미 채워져 있는 걸 보면, 지금의 `dart_facts.py` 단일연도 어댑터보다
  더 풍부한 파이프라인으로 만들어진 것으로 보입니다 — 덮어쓰지 마세요.
- 따라서 이 샘플에서 가능한 카드만 계산하고 나머지는 `null + reason`으로 남깁니다.
- 새 JSON은 반드시 `New for anti/public/data/kfa_<code>_v1.json` 아래에 둡니다.
  저장소 루트 `public/data/`는 Cloudflare asset root가 아닙니다.

```bash
cd scripts/dart
python3 -m unittest discover -s tests -v
python3 enrich_snapshot.py ../../New\ for\ anti/public/data/kfa_005930_v1.json --output /tmp/kfa_005930_enriched.json
```
