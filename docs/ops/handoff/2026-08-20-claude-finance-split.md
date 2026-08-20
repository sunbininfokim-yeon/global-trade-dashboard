# 금융 도메인 4분할 — 검증 인수인계

**브랜치:** `claude/finance-domain-split`
**롤백 지점:** `backup/pre-finance-split-20260819-210436` (태그, origin에 push됨)

## 무엇을 했나

`app.js` 9,439줄에 섞여 있던 금융 4개 도메인을 각자 파일로 분리했다.
동작 변경은 **의도적으로 0건**이다 — 코드를 옮기기만 했다.

| 파일 | 선언 수 | 내용 |
|---|---|---|
| `macro.js` | 35 | 매크로 모니터 (`mm*`, `MM_*`, `renderMacroMonitor`) |
| `market-microstructure.js` | 39 | 시장 미시구조 (`ms*`, `MS_*`, `renderMicrostructure`) |
| `calculator.js` | 40 | 기업가치 계산기 (`co*`, `kfa*`, `krx*`, `loadCompany`, `finSeriesBlock` 체인) |
| `portfolio.js` | 49 | 포트폴리오 랩 (`pf*`, `PF_*`, `renderPfInput/Result`, `finRiskRows`) |
| `app.js` | 197 | 나머지 (지도/무역/기후/해운) + 진짜 공용 `finEsc`/`finPct`/`finPlaceholder` |

`app.js`: 9,439줄 → 4,900줄.

접두사만으로 자르면 각 화면의 진입점(`renderPfInput`, `loadCompany` 등)이
app.js에 남아 분리 목적이 무너진다 — 포트폴리오 세션이 여전히 app.js를 고치게
된다. 그래서 스크립트의 `EXPLICIT` 목록에 진입점과 "한 화면만 쓰는 헬퍼 체인"을
이름으로 지정했다. 남긴 것은 호출자가 둘 이상인 것뿐이다.

UI 문구 변경 1건: 금융 드롭다운의 `파생상품` → `시장 미시구조`
(파일명도 여기 맞춰 `market-microstructure.js`).

## 왜 했나

`trade.js` 헤더에 적힌 사고가 근거다 — 여러 세션이 `app.js`를 동시에 열고,
squash merge가 diff 대신 영역 전체를 덮어써서 **무역 패널 코드가 충돌 표시
없이 main에서 사라진 적이 있다.** 도메인이 한 파일에 있는 한 이 위험은 계속된다.

분리 후에는 매크로 작업 세션과 계산기 작업 세션이 서로 다른 파일을 만지므로
같은 영역을 덮어쓸 일이 없다.

## 무손실 근거 (재현 가능)

분리는 손으로 재작성한 게 아니라 `scripts/ops/split_finance_domains.py`가
**위치 기반으로 잘라낸 것**이다. 각 최상위 선언의 바이트를 그대로 옮기고,
그 앞의 주석 블록도 함께 옮긴다(설명이 코드에서 떨어지지 않게).

스크립트는 쓰기 전에 `헤더 + 모든 조각 == 원본`을 검사하고, 실패하면
아무것도 쓰지 않는다.

검증 결과:
- 문자 구성 비교: **코드 문자 100% 일치**, 차이는 개행 4개뿐
  (파일당 1개, 각 파일 첫 코드 앞 `lstrip`)
- `node --check`: 5개 파일 전부 통과
- 브라우저: `ReferenceError`/`is not defined` **0건**
- **분리 전 버전과 나란히 비교**: 같은 서버에 분리 전 `app.js`를 올려
  4개 화면의 렌더링 결과 텍스트를 해시로 대조 — 4개 모두 길이·해시 완전 일치
  (`macro_monitor` 2374/571676123, `fin_derivatives` 4445/-449331506,
  `fin_portfolio` 2622/70807976, `fin_valuation` 2512/-1760214612)

## 로드 순서

```
macro.js → market-microstructure.js → portfolio.js → calculator.js → app.js → trade.js
```

읽는 쪽이 읽히는 쪽 뒤에 오도록 나열했다.

| 참조하는 파일 | 참조 대상 |
|---|---|
| `market-microstructure.js` | `macro.js`: `mmLineChart`, `mmWireCharts` |
| `calculator.js` | `macro.js`: `mmFmt` |
| `calculator.js` | `portfolio.js`: `pfSearchLocal`, `pfSearchRemote`, `pfSpot`, `pfFromQuote`, `pfLoadRefs` (검색창이 포트폴리오의 시세 조회를 재사용) |
| `macro.js` | `app.js`: `deckgl`, `worldBaseLayers`, `mapContainer` 등 지도 전역 |
| `app.js` | 각 도메인의 `render*` 진입점 **4개뿐** (분리 전 41개에서 감소) |

교차 참조는 **전부 함수 본문 안**이라 실행 시점에 해결된다. 로드 시점에 다른
파일을 참조하는 최상위 초기화는 4개 파일 모두 0건임을 확인했으므로, 위 순서는
의존성을 문서화하는 것이지 강제하는 것은 아니다.

## 코덱스 검증 요청 사항

현재 배포본(main)과 이 브랜치를 나란히 놓고 봐 주면 좋겠다.

1. **동작 동일성** — 아래 4개 화면에서 분리 전/후 차이가 있는지
   - 금융 › 매크로 모니터: 국가 클릭 → 카테고리 탭 → 지표 클릭 → 차트
   - 금융 › 호가 및 유동성: 4개 탭 전환, 가격대별 체결 클릭, 신용 차트
   - 금융 › 포트폴리오 계산기: 종목 검색 → 추가 → 계산 → 뷰 전환
   - 금융 › 기업 가치 계산기: 종목 검색 → 카드 → DCF/역DCF 패널
2. **콘솔** — `ReferenceError` 계열이 하나라도 나오면 그게 분리 실패 신호다
   (`/api/*` 404는 로컬 정적 서버에선 정상)
3. **놓친 도메인 코드** — `app.js`에 남은 197개 선언 중 금융 화면에서만
   쓰이는 게 더 있는지. `fin*` 중 `finEsc`(5개 파일 전부 사용),
   `finPct`(app+포트폴리오), `finPlaceholder`(app만)는 공용이라 남겼고,
   나머지 `fin*`(`finSeriesBlock`/`finPeriodBars`/`finNormPeriods`/`finTipEnsure`
   → 계산기 전용, `finRiskRows`/`finSignedPct`/`FIN_LOCALE` → 포트폴리오 전용)는
   옮겼다. 이 구분이 맞는지 봐 주면 좋겠다.

## 롤백

```bash
git checkout main && git reset --hard backup/pre-finance-split-20260819-210436
```

배포까지 되돌리려면 그 뒤 `npx wrangler deploy`.

## 남은 것

- 이 레포는 PR merge가 배포로 이어지지 않는다. 수동 `npx wrangler deploy` +
  KV 캐시 삭제(`macro:v1:*`)가 필요하다. 자동화는 별도 작업으로 남겨 둔다.
- `macro_monitor.js`(480줄)는 app.js를 건드리지 않는 **미사용 프로토타입**이다.
  실제 매크로 코드는 이번에 `macro.js`로 나온 쪽이다. 정리 대상이지만 이번
  범위에는 넣지 않았다.
