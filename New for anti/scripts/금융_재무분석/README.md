# 금융_재무분석 — Personal Portfolio Lab

글로벌 트레이드 대시보드 **금융/제조 창** 하위에 붙일 개인 포트 진단 파이프라인.

- 데이터: Yahoo Finance chart API 우선, 실패 시 Stooq CSV 일봉 폴백 (거래소 직접 API 불필요)
- 이론: Ledoit–Wolf Σ · EWMA(단기) · HRP · 위험기여 · 단기/장기 VaR · Sharpe
- 산출: `public/data/portfolio_analysis_v1.json` (UI는 이 JSON을 fetch)

> **UI 연결:** `app.js` / 금융 창 마크업은 Claude Code 소유.  
> 이 폴더는 **분석 파이프라인 + 데이터 계약**만 담당한다.

## 빠른 실행

```bash
cd "New for anti/scripts/금융_재무분석"
python3 run_pipeline.py --portfolio samples/demo_portfolio.json
```

옵션:

```bash
python3 run_pipeline.py \
  --portfolio samples/demo_portfolio.json \
  --out "../../public/data/portfolio_analysis_v1.json" \
  --base-currency KRW
```

오프라인(캐시만):

```bash
python3 run_pipeline.py --portfolio samples/demo_portfolio.json --cache-only
```

## 가격 소스

1. **Yahoo** chart API (`query1`) — 기본  
   실패 시 같은 Yahoo 계열로 `query2` → 기간 단축(2Y) → `v7/finance/download` CSV 재시도
2. **Stooq** 일봉 CSV — `AAPL`→`aapl.us`, `005930.KS`→`005930.ks`, `USDKRW=X`→`usdkrw` 등 심볼 매핑 후 best-effort  
   (JS bot challenge에 막히면 조용히 실패하고 다음으로 넘어감 / 전부 실패 시 에러)

성공 소스는 `data_quality.price_sources` 와 캐시 사이드카 `*.meta.json`에 기록됩니다.  
(Investing.com 스크래핑은 ToS/취약성 때문에 의존하지 않습니다 — 향후 옵션으로만 메모.)

## 파이프라인

```text
portfolio JSON
  → normalize (NAV·신용 원장 검증 → 단순 계좌만 residual KRW cash; top MAX_NAMES=20 by |value|)
  → resolve (alias → canonical id → Yahoo symbol)
  → prices (Yahoo daily → Stooq CSV fallback; csv + .meta.json cache)
  → returns (base currency 통일)
  → Σ_short (EWMA) / Σ_long (Ledoit–Wolf)
  → metrics (return, vol, Sharpe, VaR/CVaR, risk contrib)
  → HRP 대안 비중 + Δweights
  → portfolio_analysis_v1.json
```

## 입력 포맷

`samples/demo_portfolio.json` 참고. 각 포지션은 `query`(티커·한글명·종목코드) + `value`(원화 평가액) 또는 `weight`.

### 순자산(NAV)·신용 — 선택

| 필드 | 설명 |
|------|------|
| `net_asset_value` 또는 `nav` | 권장 입력. 계좌 **순자산**(원화) |
| `total_value` 또는 `aum_krw` | 구 입력 호환 별칭이며 NAV로 해석 |
| `credit_used_krw` (`margin_debt_krw` 별칭) | 신용·미수 원금(원화). 총노출이 아니라 부채로 별도 기록 |
| 단순 롱·현금 계좌의 합 < NAV | 잔여를 **원화 현금**(`query: 원화` / `cash:krw`)으로 자동 배정(기존 현금 줄에 합침) |
| 공매도 또는 신용 계좌 | `Σ(부호 있는 position.value) − credit_used_krw = NAV`를 만족해야 함. 현금·담보를 직접 입력하며 자동 잔여 현금 없음 |

```json
{
  "net_asset_value": 10000000,
  "positions": [
    { "query": "엔비디아", "value": 7000000 }
  ]
}
```
→ 잔여 300만원이 원화 현금으로 들어갑니다.

신용 사용 예시(1억 순자산으로 1.3억 롱 노출):

```json
{
  "net_asset_value": 100000000,
  "credit_used_krw": 30000000,
  "positions": [
    { "query": "삼성전자", "value": 130000000 }
  ]
}
```

이 경우 총노출은 1.3억(130% of NAV)이고, 금액 VaR은 1.3억이 아니라 1억 NAV를 기준으로 표기합니다. 위험수익률 계산도 130% 노출을 그대로 반영합니다.

정규화 순서는 **(1) 잔여 현금 배정 → (2) 상위 `MAX_NAMES` 절단** 입니다.  
상수 위치: `portfolio_lab/normalize.py` 의 **`MAX_NAMES = 20`** (30 상향 시 이 값만 바꾸면 됨 · Claude UI 입력 한도와 동기).

절단: 포지션 수 > 20이면 `\|value\|`(또는 weight mode는 `\|weight\|`) **큰 순 20개**만 분석.  
잘린 줄은 `data_quality.truncated_positions` / `positions_truncated_ko|en`에 기록하며, 가짜 ‘기타’ 시계열로 넣지 않습니다. 원화 현금이 크면 그대로 상위권에 남습니다.

### 규모 구간 가이드 (개인 100만~5억 휴리스틱)

정규화 후 총액으로 `size_guide` 를 리포트에 넣습니다 (MPT 종목수 공식 아님).

| bucket | 대략 구간 | 권장 라인 수 |
|--------|-----------|--------------|
| micro | < 500만 | 3–8 · ETF 우선 |
| small | 500만–3천만 | 5–15 |
| standard | 3천만–1억 | 8–20 |
| large | 1억–5억 | 10–30 |
| overload | > 5억 | 참고 구간 밖 주석 |

### 채권·원자재

레지스트리/`asset_class: bond`·commodity 라인(미국채권 AGG, 일본국채, 금 등)도 **종목 수 20 캡·공분산·HRP에 동일 포함**됩니다. “주식 전용” 모델이 아닙니다.

### 종목 해석 (registry + Yahoo passthrough)

| 입력 유형 | 동작 |
|-----------|------|
| **한글명 / 별칭** | `instruments/registry.json` 별칭 매칭 (예: `삼성전자`, `코스피`, `스페이스X`) |
| **티커 직접 입력** | 레지스트리에 없어도 Yahoo 심볼처럼 보이면 동적 종목 `dyn:yahoo:{SYMBOL}` 생성 |

예시:

- SpaceX 관련 → 레지스트리 `SPCX` (별칭: 스페이스X, SpaceX) 또는 티커 `SPCX` 직접
- 코스피 지수 → `코스피` / `^KS11` · 코스피200 ETF → `KODEX200` / `069500`
- 미등록 티커 → `AAPL`, `005930.KS`, `EURUSD=X` 등 그대로 passthrough
- 홍콩 CSOP SK하이닉스 일간 2배 → `7709`, `7709.HK`, `CSOP 하이닉스 2배` (HKD 실제 상장 가격). 기존 `하이닉스2배`는 현물×2 프록시이므로 서로 다릅니다.

통화 추정: `.KS`/`.KQ`→KRW, `.T`→JPY, `=X`→FX, 그 외→USD (USD 종목은 기존처럼 USDKRW로 원화 환산).

## 투자 성향

```bash
python3 run_pipeline.py --portfolio samples/user_balanced_portfolio.json --risk-profile balanced
```

`conservative` / `balanced` / `aggressive` — 현금·VaR 한도만 다르고, 기대수익률 가정은 없습니다.

## 종목 자동완성 (UI용)

```bash
python3 run_pipeline.py --suggest "삼성전"
```

## 화면 문구 (basic vs expert)

산출 JSON에 카피 블록이 두 세트 있습니다. UI는 모드만 고르면 됩니다.

| 모드 | 키 | 용도 |
|------|-----|------|
| **basic** | `ui_copy_basic_ko` / `ui_copy_basic_en` | 사무/실무 표현. 카드 제목에 VaR·샤프를 쓰지 않음 (예: 예상 등락 폭, 단기 손실 가능 규모, 현금·대기자금). 현금은 성향 `cash_min`/`cash_max` 밴드를 공식 목표로 안내. |
| **expert** | `ui_copy_ko` / `ui_copy_en` | 변동성·샤프·VaR 등 지표명 포함. |

로케일만 골라 같은 카드 스키마를 쓰면 됩니다. 상세 필드 목록은 `DATA_CONTRACT.md` 참고.

## Golden tests

고정 샘플 포트 + `cache/prices` 캐시로 엔진을 돌린 뒤, 핵심 지표를 `tests/golden/*.json`과 비교합니다. 브라우저가 SoT이면 브라우저 export 숫자로 golden을 갱신하세요.

```bash
cd "New for anti/scripts/금융_재무분석"
python3 -m unittest discover -s tests -v
```

상세: `tests/golden/README.md`.
