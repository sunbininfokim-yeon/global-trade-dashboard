# 금융 도메인 4분할 — 검증 인수인계

**브랜치:** `claude/finance-domain-split`
**롤백 지점:** `backup/pre-finance-split-20260819-210436` (태그, origin에 push됨)

## 무엇을 했나

`app.js` 9,439줄에 섞여 있던 금융 4개 도메인을 각자 파일로 분리했다.
동작 변경은 **의도적으로 0건**이다 — 코드를 옮기기만 했다.

| 파일 | 선언 수 | 내용 |
|---|---|---|
| `macro.js` | 34 | 매크로 모니터 (`mm*`, `MM_*`) |
| `market-microstructure.js` | 38 | 시장 미시구조 (`ms*`, `MS_*`) |
| `calculator.js` | 31 | 기업가치 계산기 (`co*`, `CO_*`, `kfa*`, `KFA_*`) |
| `portfolio.js` | 43 | 포트폴리오 랩 (`pf*`, `PF_*`) |
| `app.js` | 214 | 나머지 (지도/무역/기후/해운/공용 헬퍼) |

`app.js`: 9,439줄 → 6,036줄.

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
- 4개 화면(`macro_monitor`/`fin_derivatives`/`fin_portfolio`/`fin_valuation`)
  전부 렌더링 확인

## 로드 순서 (중요)

`index.html`에서 순서가 곧 의존성 해결이다. 모듈이 아니라 평범한 스크립트라
전역 스코프를 공유한다.

```
macro.js  →  market-microstructure.js  →  calculator.js  →  portfolio.js  →  app.js  →  trade.js
```

`macro.js`가 먼저여야 하는 이유 — 교차 호출이 **정확히 4건** 있고 전부
macro를 향한다:

| 호출하는 쪽 | 호출되는 것 |
|---|---|
| `msHistChart` | `mmLineChart` |
| `msModalFor` | `mmLineChart` |
| `coDcfPanel` | `mmFmt` |
| `coReversePanel` | `mmFmt` |

다만 이 4건은 모두 **함수 본문 안**이라 실행 시점에 해결된다. 로드 시점에
다른 파일을 호출하는 최상위 초기화는 4개 파일 모두 0건임을 확인했다
(그래서 순서가 틀려도 당장 깨지진 않지만, 위 순서를 지키는 게 맞다).

## 코덱스 검증 요청 사항

현재 배포본(main)과 이 브랜치를 나란히 놓고 봐 주면 좋겠다.

1. **동작 동일성** — 아래 4개 화면에서 분리 전/후 차이가 있는지
   - 금융 › 매크로 모니터: 국가 클릭 → 카테고리 탭 → 지표 클릭 → 차트
   - 금융 › 호가 및 유동성: 4개 탭 전환, 가격대별 체결 클릭, 신용 차트
   - 금융 › 포트폴리오 계산기: 종목 검색 → 추가 → 계산 → 뷰 전환
   - 금융 › 기업 가치 계산기: 종목 검색 → 카드 → DCF/역DCF 패널
2. **콘솔** — `ReferenceError` 계열이 하나라도 나오면 그게 분리 실패 신호다
   (`/api/*` 404는 로컬 정적 서버에선 정상)
3. **놓친 도메인 코드** — `app.js`에 남은 214개 선언 중 금융 화면에서만
   쓰이는 게 더 있는지. 특히 `fin*` prefix 헬퍼들은 4개 도메인이 공유해서
   일부러 `app.js`에 남겼는데, 이 판단이 맞는지 봐 주면 좋겠다.

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
