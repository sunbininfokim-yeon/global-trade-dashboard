# 당신이 준비·찾아 주면 되는 것들

엔진은 픽스처로 이미 돌아갑니다. **실데이터·본인 포트**로 바꾸려면 아래만 있으면 됩니다.

## 필수 (실사용)

| 항목 | 어디에 쓰나 | 어떻게 |
|------|-------------|--------|
| **OpenDART API 키** | 한국 기업 재무 | [opendart.fss.or.kr](https://opendart.fss.or.kr) 인증키 → `export DART_API_KEY=...` |
| **내 포트 보유 목록** | 샤프·분산 | 종목코드 + 비중(또는 금액). `scripts/portfolio/config/holdings.example.json` 복사해서 수정 |

예시 holdings:

```json
{
  "risk_free_annual": 0.035,
  "holdings": [
    {"ticker": "005930.KS", "weight": 0.5, "industry_kit": "electronics", "name_ko": "삼성전자"},
    {"ticker": "011200.KS", "weight": 0.5, "industry_kit": "shipping", "name_ko": "HMM"}
  ]
}
```

## 있으면 좋은 것 (정확도↑)

| 항목 | 용도 |
|------|------|
| **무위험금리** | 샤프·(나중) WACC. 예: 국고 3년 %. 기본 3% |
| **본인 WACC / 목표 배수 감** | DCF Bull·Bear 슬라이더 기본값. 없어도 엔진 프리셋 사용 |
| **주식 수(또는 시가총액)** | 주당 적정가. 없으면 기업가치(EV/Equity) 밴드만 |
| **SEC 볼 미국 종목 리스트** | 티커만. API 키 불필요, User-Agent용 이메일 하나 |

## 지금은 안 줘도 되는 것

- PE 수업 PDF (표준 DCF·배수면 충분)
- 산업 키트 정의 (전자/조선/해운은 코드에 이미 있음)
- 주석 PDF 전부 (나중에 표 파서 단계)
- 증권사 리포트 (가정 프리셋 추천용 — 후순위)

## 가격 데이터 (포트폴리오)

지금 스냅샷은 **오프라인 수익률 픽스처/합성**입니다.  
실전 샤프를 내려면 다음 중 하나:

1. 직접 CSV/JSON으로 일별 수익률 제공, 또는  
2. Yahoo 등 무료 시세 연동 허용 (티커 `.KS` / `.KQ`)

원하시면 2번 어댑터를 다음에 붙입니다.

## 실행 (키 없이 데모)

```bash
cd "New for anti/scripts/dart"
python3 -m unittest discover -s tests -v
python3 build_universe.py --seed --print-stats

cd "../portfolio"
python3 tests/make_returns_fixture.py
python3 -m unittest discover -s tests -v
python3 build_portfolio_risk.py --print-stats
```
