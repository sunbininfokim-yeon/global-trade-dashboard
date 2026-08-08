# Portfolio risk (Sharpe / diversification)

보유 비중 → 수익률 시계열 → **샤프, HHI(유효 종목 수), 평균 상관, 분산 점수**.

재무 엔진(`scripts/dart`)과 축이 다릅니다. 산업 키트 태그만 공유합니다.

```bash
python3 tests/make_returns_fixture.py   # 데모용 수익률
python3 -m unittest discover -s tests -v
python3 build_portfolio_risk.py --holdings config/holdings.example.json --print-stats
# → ../../public/data/portfolio_risk_v1.json
```

본인 포트: `config/holdings.example.json` 복사 후 비중 수정.  
실전 가격 연동·준비물: `../dart/USER_INPUTS.md`.
