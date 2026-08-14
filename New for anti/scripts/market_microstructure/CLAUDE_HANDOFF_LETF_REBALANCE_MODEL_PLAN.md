# Claude handoff — 하닉·삼성 단일종목 LETF 관측/추정 리밸런싱 설계

## 결론과 범위

이번 보강은 **예측 모델**이 아니라, KRX EOD 공개 데이터로 만드는 세 층의
모니터링 패널이다. 대상은 SK하이닉스(`000660`)와 삼성전자(`005930`)다.

1. **관측 AUM 추이** — 단일종목 레버·인버스 ETF의 일별 합계 순자산
2. **관측 유동성 비율** — LETF 거래대금 ÷ 같은 날 해당 현물 거래대금
3. **추정 리밸런싱 압력** — 일일 리셋 구조에서 도출한 EOD 기계적 프록시

1·2는 이미 공용 `stock_letf_history_v1.jsonl`과 `msStockLetfSeries()`의
기반이 있다. 새 데이터 작업은 3의 **원시 일별 값**만 추가한다. Claude는
이를 같은 D 모달 안에서 세 번째 차트로 연결한다.

이 설계는 실제 ETF 체결, AP 설정/환매, 스왑·선물 헤지, 딜러 감마, 또는
가격 영향의 관측이 아니다. 그와 같이 표시하거나 해석하지 않는다.

## 데이터 계약 — Codex 소유

파일: `public/data/stock_letf_history_v1.jsonl`  
키: `date + ticker`  
공통 필수 메타데이터: `date`, `as_of`, `source`, `quality`

기존의 AUM·거래대금 필드는 바꾸지 않고, 각 하닉·삼전 행에 아래 원시 필드를
추가한다.

```json
{
  "underlying_day_return": -0.032,
  "implied_rebalance_krw": -123456789000.0,
  "implied_ir_pct": 4.18,
  "implied_rebalance_quality": "estimated",
  "implied_rebalance_formula": "Σ AUM × (L² − L) × underlying daily return; EOD mechanical proxy, not observed ETF trades"
}
```

- `implied_rebalance_krw`: **부호가 있는** 원화 추정치. 양수=모형상 순매수
  방향, 음수=모형상 순매도 방향.
- `implied_ir_pct`: `abs(implied_rebalance_krw) / spot_trading_value_krw × 100`.
  강도이며 방향은 `implied_rebalance_krw`에서만 읽는다.
- `quality`는 AUM·거래대금 등 원시 입력의 품질이다. 모델 산출은 별도
  `implied_rebalance_quality: "estimated"`로 구분한다.
- `day_return` 또는 유효한 상품 AUM/레버리지가 없으면 두 수치는 **null**이다.
  0, 직전값, 휴장일 보간을 쓰지 않는다.

`implied_rebalance_krw`, `implied_ir_pct`가 Claude UI가 참조할 정확한 이름이다.
7거래일 이동평균은 JSONL/파이프라인에서 만들지 않는다.

## 계산식과 해석 경계

상품 `i`마다 다음을 계산한다.

```text
TR_i = AUM_i × (L_i² − L_i) × R_t
implied_rebalance_krw = Σ TR_i                 # total_rebalance(...)["tr_total"]
implied_ir_pct = |Σ TR_i| / 현물 당일 거래대금 × 100
```

- `AUM_i`, `L_i`, `R_t`는 KRX EOD 스냅샷의 해당 거래일 값이다.
- 기존 `engine.py`의 `realized_ir_pct`/시나리오에는 `tr_abs_sum`이 쓰인다.
  이 새 지표에 그것을 재사용하면 안 된다.
- 다만 현재 유니버스의 표준 `L=+2`, `L=-1`, `L=-2`에서는 모두
  `L²−L ≥ 0`이다. 따라서 같은 날의 `TR_i`는 같은 `R_t` 부호를 가지며,
  현재 상품 구성에서는 `tr_total`과 `tr_abs_sum`이 **수치상 같을 수 있다**.
  “롱·인버스가 이 식에서 상쇄돼 반드시 다른 수치가 난다”라고 설명하면 안 된다.
  `tr_total`을 저장하는 이유는 방향이 있는 순합 정의를 명확히 하고, 향후
  비표준 상품/베타 모델을 추가하더라도 계약을 유지하기 위해서다.

이 값은 하루 종가 기준의 기계적 크기 추정이다. 장중 체결 시점, 설정·환매,
상품별 복제 방식, 비용, 베타, 스왑/선물 헤지를 반영하지 않는다.

## AUM과 상품 유니버스 품질 규칙

- KRX `etp/etf_bydd_trd`의 실제 순자산 필드가 있으면 그것을 사용한다.
- 실제 순자산이 없고 시가총액만 있으면 그 상품/행은 `partial`로 태그하고,
  UI 라벨은 “순자산 프록시”로 낮춘다. 실제 AUM과 같은 선으로 조용히 섞지
  않는다.
- 백필은 **날짜별 KRX ETF 목록**에서 하닉·삼성전자 + 레버리지/인버스 이름을
  찾아야 한다. 현재 정적 `letf_universe.json`만 사용하면 신규·과거 상품을
  누락할 수 있다. 알려진 상품은 카탈로그의 `L`을 우선하고, 미등록 상품은
  이름에서 `L`을 유추하되 유추 불가 시 `partial`/null로 남긴다.
- KRX `sto/stk_bydd_trd`의 `ACC_TRDVAL`은 해당 날짜 현물 거래대금 분모로
  사용한다. 롤링 ADV라고 부르지 않는다.

## 백필과 공백 조사 — Codex 소유

`backfill_single_stock_letf_history.py`는 KRX `sto/stk_bydd_trd`와
`etp/etf_bydd_trd`만 사용하고, 과거 날짜에 현재 Naver 투자자 수급을 섞지 않는다.
KRX Secret은 `KRX_API`만 사용하며 코드·로그·JSON에 절대 기록하지 않는다.

현재 알려진 행은 2026-08-07과 2026-08-13뿐이다. 8월 8일·9일은 주말이므로
공백 진단 대상 거래일은 **8월 10일·11일·12일**이다. 원인을 다음 순서로
확인한다.

1. 해당 날짜의 GitHub Actions 실행/실패/병합 시점
2. `build_market_microstructure.py --live`가 KRX 대신 FDR로 폴백했는지
3. `append_derivatives_history.py`가 실행·커밋 allowlist에 포함됐는지
4. KRX 응답이 비어 있었는지, 스키마 검증이 실패했는지

실제 KRX 값이 조회된 날만 append한다. 휴장일·오류일·권한 오류일은 행을 만들지
않고, 원인과 날짜를 보고한다.

## UI 구현 지시 — Claude 소유

Codex는 `New for anti/app.js` 및 `.github/workflows/**`를 수정하지 않는다.
Claude는 별도 `claude/` 브랜치에서 아래를 구현한다.

1. D의 하닉 `추이`를 `alert_letf`가 아니라 `stock_letf:000660`으로 라우팅한다.
   알림 카드만 `alert_letf`를 사용한다. 두 스냅샷의 `as_of`가 다르면 섞지 않는다.
2. 하닉·삼전 D 모달에 세 차트를 분리한다.
   - **단일종목 LETF AUM 추이** (관측/프록시 상태 표시)
   - **LETF 거래대금 / 현물 거래대금** (관측)
   - **모델 추정 리밸런싱 압력**: raw `implied_ir_pct`와 7관측거래일 평균,
     방향은 `implied_rebalance_krw` 툴팁/표에 병기
3. 세 번째 차트에는 항상 다음을 표시한다.
   > 모델 추정 리밸런싱 압력입니다. 실제 ETF 체결·딜러 헤지·가격 영향을 뜻하지 않습니다.
4. B/C/D와 파생 수급의 공용 히스토리 차트는 **관측 5거래일 미만이면 선을
   그리지 않는다**. 대신 `히스토리 축적 중 N/5`와 실제 관측 표를 표시한다.
   현재의 `<2` 조건만으로는 두 점 직선 그래프 문제가 남는다. 휴장일은 채우지
   않는다.
5. 구현 후 각 카드와 모달을 실제 배포/로컬 화면에서 클릭 검증한다.

## 인수 기준

### Codex 데이터 테스트

- `L=+2`, AUM=100, R=+5% → TR=+10
- `L=-2`, AUM=100, R=+5% → TR=+30
- 두 상품이면 `tr_total=+40`; 현물 거래대금=1,000이면 `implied_ir_pct=4.0`
- 음수 수익률이면 TR 부호도 음수
- `day_return=null`, 빈 상품, 불완전 AUM은 새 두 지표가 null
- `date+ticker` 중복만 교체, 주말/휴장일 신규 행 없음

### Claude UI 검증

- 하닉 D와 알림 카드가 서로 다른 모달/기준일을 명확히 유지
- 4관측 이하에서 두 점 직선 그래프가 나오지 않음
- 5관측 이상에서만 AUM·비율·원시 IR이 선 그래프로 렌더
- 7관측 이상에서만 7관측거래일 평균선 렌더
- quality/as_of/source 및 estimated 고지가 모든 D 차트에서 확인됨

## PR 분리

- **Codex PR:** JSONL 계약, 계산, KRX 실측 백필, 단위 테스트, 이 문서
- **Claude PR:** `app.js` 라우팅/차트/문구/5일 폴백 및 필요 워크플로 실행
- 둘은 별도 PR로 머지하고, Claude는 Codex PR의 정확한 필드명을 확인한 뒤 UI를
  연결한다.
