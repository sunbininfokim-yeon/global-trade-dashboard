# Codex review — 수급 불균형이 해외 LETF 보드를 읽는다 (HK 재소싱)

**Branch:** `claude/market-microstructure-letf-integration-28gc91`
**PR:** https://github.com/sunbininfokim-yeon/global-trade-dashboard/pull/297 (draft)
**HEAD at handoff:** `d89f589`
**작성:** Claude Code · 2026-09-12
**Scope:** `fetch_external_venues.py` 의 HK 경로 · `engine.py` global stack ·
`ai_casino_brief.py` 랭킹 · `external_history.py` 날짜 · D 표 UI 열
**Not in scope:** `build_overseas_letf.py` / `overseas_letf.py` **본체는 건드리지 않았다.**
수집기 로직·유니버스·워크플로 모두 그대로다. 국내 LETF·파생·신용·가격대별 탭도 무관.

---

## 왜 Codex에게 보내는가

이 변경은 **소유권 경계를 넘는다.**

- `market-microstructure.js:15` 가 `scripts/market_microstructure` 를 **Cursor 소유**로 명시
- 해외 보드(`build_overseas_letf.py`, `overseas_letf.py`, `overseas_letf_universe.json`)는
  `OVERSEAS_LETF_HANDOFF.md` 기준 **Codex 작성**
- `CLAUDE.md` 의 Claude 단독 소유 목록에 `scripts/market_microstructure/**` 는 없다

바뀐 8개 파일 중 **UI는 `market-microstructure.js` 하나뿐**이고 나머지는 엔진 쪽이다.
그리고 이 PR은 **Claude 소유 코드가 Codex 소유 데이터 계약에 새로 의존하게 만든다.**
계약 소유자의 확인이 필요한 지점이 여기다.

---

## Start here (read in order)

1. **이 파일** — 계약과 체크리스트
2. `fetch_external_venues.py` — `hk_products_from_board()` / `_hk_tv_ratio_by_underlying()`
3. `market_microstructure/engine.py` — `global_leverage_stack`, `external_vs_spot`
4. `market_microstructure/external_history.py` — `_row_from_product()` 날짜 분기
5. `tests/test_microstructure.py` — 신규 9건
6. `DATA_SOURCES.md` §3 — 개정된 출처 문구

---

## 무엇을 고쳤나 (한 줄)

`수급 불균형` 탭과 `해외 LETF` 탭이 **같은 홍콩 펀드(7709/7747/7347)를 각자 수집**하고
있었고 값이 달랐다. 스냅샷 쪽을 버리고 **보드를 단일 출처로** 삼았다.

| 7709.HK | 이전 (스냅샷·Yahoo) | 이후 (보드) |
|---|---|---|
| AUM | `$550,114,461` | `null` |
| 배율 L | `2` (config 고정) | `null` (미공개) |
| 환율 | `usdhkd = 7.8` 상수 | 날짜별 FX |

CSOP는 **2026-08-03부터 가변 배율**이고 당일 목표를 공개하지 않는다
(`letf_universe.json` 에도 `L_flexible: true`). 그런데 코드는 `p.get("L", 2)` 로 2를 썼다.
결과적으로 `hk_notional_usd = 1100228923.08` 이 센트 단위까지, `hk_over_spot_adv` 가
"하이닉스 현물 ADV의 18.6%" 로 **실측처럼** 렌더링됐다.

대체 지표는 가정이 필요 없는 쪽이다 — `etf_to_kr_cash_tv_ratio`.

---

## 새로 생긴 계약 의존 (핵심 검토 대상)

`fetch_external_venues.py` 가 `public/data/overseas_letf_board_v1.json` 에서 읽는 필드.
**Codex가 이 이름·의미를 바꾸면 수급 불균형 탭이 조용히 빈다.**

`products[].latest` 에서:

| 필드 | 쓰임 | 없으면 |
|---|---|---|
| `date` | 관측일. 히스토리 append 날짜 + 비율 버킷 앵커 | 행이 `quality=missing` |
| `etf_to_kr_cash_tv_ratio` | **D 표 홍콩 열의 값** | 열이 `—` |
| `leverage` | 노셔널 계산 | 노셔널 `null` |
| `aum_usd` / `aum_as_of` | 노셔널 계산 | 노셔널 `null` |
| `trading_value_usd` | 커버리지 완전할 때 거래대금 | 아래로 폴백 |
| `covered_trading_value_usd` | 부분 커버리지 폴백 | 거래대금 `null` |
| `coverage_complete` | 위 둘 중 선택 + 플래그 표시 | `False` 취급 |
| `valued_listing_count` / `expected_listing_count` | 커버리지 표시 | `null` |
| `direction` | long/inverse 분리 | config 값 폴백 |

`products[]` 최상위에서: `name` · `structure` · `leverage_ceiling` · `stale` ·
`data_age_calendar_days` · `listings[].ticker` + `listings[].venue == "hk"`

**venue 매칭 규칙:** `listings[].venue == "hk"` 인 상품만 이 경로에 들어온다.
CSOP 3종의 HK 상장이 이 값을 유지해야 한다.

**실행 순서:** `run_daily.sh` 에서 `build_overseas_letf.py` 가
`build_market_microstructure.py` **보다 먼저** 돈다. 이미 그렇게 돼 있어 순서 변경은 없다.
보드 파일이 없으면 `load_overseas_board()` 가 `None` 을 주고 HK 행 전체가 `missing` 이 된다.

---

## 리뷰에서 잡힌 것 (전부 수정 완료, 재검증 요청)

자체 `/code-review high` 로 7건 — 4건 재현 확인.

1. **HK 히스토리 로그가 끊겼다.** `_row_from_product` 가 `yahoo.last_bar.as_of` 로만
   날짜를 잡는데 보드 행엔 Yahoo 페이로드가 없다 → HK 3행 → **0행**. 미국 행은 계속
   쌓여서 "no dated Yahoo bars" 경고도 안 떴다. `observed_on` 을 받도록 수정, 3행 복구.
2. **비율 버킷의 `as_of` 가 config 첫 행에 고정.** 오래된 펀드가 앞에 있으면 그게 날짜를
   잡고 최신 행을 배제 → 몇 주 지난 비율이 오늘 값으로. 최신 관측일 기준으로 수정.
3. **`largest_product` 가 `L=None · notional $Nonebn` 렌더.** 바로 아래 마크다운 표는
   같은 이유로 고쳐놓고 이 문자열만 빠뜨렸다.
4. **부분 커버리지 subtotal 을 펀드 거래대금으로 발행.** `coverage_complete` 반영.
5. `_sum_exp_strict` 가 HK 에만 적용 → US/crypto 는 여전히 0.0. 셋 다 strict 로.
6. `quality` 가 관측일이 아니라 상품 행 존재 여부로 판정 → 전부 null 인데 `"observed"`.
7. 보드의 `stale` / `data_age_calendar_days` 유실 → 전달하도록 수정.

---

## 날짜가 어긋난다 (설계상 정상 — 확인 요청)

| | 관측일 |
|---|---|
| 국내 (`market_microstructure_v1.json`) | 2026-09-10 |
| 홍콩 (`overseas_letf_board_v1.json` latest) | **2026-09-09** |

해외 수집이 국내 배치보다 한 거래일 앞선 날짜까지만 확정하기 때문이다.
따라서 D 표의 두 열은 **분모의 정의만 같고 같은 날이 아니다.**

UI 문구를 그렇게 고쳤고, 홍콩 셀은 관측일을 **항상** 표시한다(원래는 다를 때만 표시해서
하필 정상 케이스를 가렸다). 날짜가 다르면 국내 날짜를 괄호로 병기한다.

> **Codex 확인 요청:** 이 하루 차이가 항상 1거래일인가, 아니면 휴장·수집 실패로
> 더 벌어질 수 있나? 후자면 UI에 임계(예: 3거래일 초과 시 경고)를 둘지 판단이 필요하다.

---

## Checklist

- [ ] `latest` 필드 9개 이름·의미가 위 표와 일치하고, 향후 변경 시 알려줄 수 있는가
- [ ] `listings[].venue == "hk"` 가 CSOP 3종에 대해 안정적인가
- [ ] `etf_to_kr_cash_tv_ratio` 를 `kr_single_stock` 에만 채우는 규칙이 유지되는가
      (ADR·바스켓이 새는 순간 D 표에 잘못된 분모가 들어온다)
- [ ] `coverage_complete=False` 일 때 `trading_value_usd` 를 `null` 로 두는 계약이 맞는가
- [ ] 노셔널을 `leverage_ceiling` 으로 계산하지 않은 판단에 동의하는가 (상한 ≠ 노출)
- [ ] 보드가 `leverage` 를 채우기 시작하면 스냅샷 노셔널이 자동 복구되는가
- [ ] 히스토리 append 가 `observed_on` 날짜로 들어가는 게 `external_leverage_history_v1.jsonl`
      기존 행들과 충돌하지 않는가 (key = date+venue+ticker)
- [ ] 날짜 어긋남 상한에 대한 판단 (위 §)

---

## 검증 상태

| | 결과 |
|---|---|
| `python3 -m unittest discover -s tests` | **84 통과** (skip 2) |
| `validate_ui_contracts.py` | 통과 |
| `node --check market-microstructure.js` | 통과 |
| 뮤테이션 검증 | 확인된 버그 4건, 수정 전 코드에서 신규 테스트가 실제로 실패함을 확인 |

---

## Gaps — 확인 못 한 것

- **`--live` 전체 실행 미검증.** KRX 키와 외부 네트워크가 필요한데 작업 환경에서
  `www.direxion.com` 등이 프록시 차단이었다. 오프라인 경로(저장된 보드 + fixture)까지만
  검증했다. **첫 `run_daily.sh` 실행 후 `external_leverage_history_v1.jsonl` 에 HK 행이
  실제로 붙는지 확인 필요.**
- **US/crypto 가 미관측으로 뜨는 건 이 환경 한정.** Yahoo·Binance 도달 불가 때문이고,
  이제 0.0 대신 `null` 로 정직하게 빠진다. 정상 환경에선 값이 들어와야 한다.
- **Direxion 5종 holdings 는 여전히 비어 있다.** 핸드오프 기록의 HTTP 403 은 봇 차단이지
  데이터 부재가 아니므로 러너에서는 될 수도 있다. 이 PR 범위 밖 — 별건.

---

## 다음 단계 (이 PR 아님, 사용자와 합의됨)

`해외 LETF` 탭 해체 검토. 15종 중 9종이 내부 구성 데이터가 없어(CSOP·LS 유럽은
구조적으로 미공개) 독립 탭 분량이 안 된다. 글로벌 지수·업종 상품(SOXL/TQQQ/TECL/KORU)은
이미 `해외-국내 선행` 탭의 하방 채널 드라이버로 쓰이고 있어 중복이다.
**이건 Codex 소유 수집기가 아니라 UI 배치 문제이므로 별도 PR로 간다.**
