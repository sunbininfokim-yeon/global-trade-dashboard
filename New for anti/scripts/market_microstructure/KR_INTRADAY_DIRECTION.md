# 장중 방향 연구 엔진

`kr_intraday_direction_engine.py`는 KOSPI·삼성전자·SK하이닉스의 시가 대비 장중 방향을 개장 전에 계산한다.

- `first15_vs_open`은 정규장 시작 후 첫 15분 봉의 종가와 당일 시가를 비교한다.
- `close_vs_open`은 당일 정규장 종가와 당일 시가를 비교한다.
- 각 출력의 `up`과 `down`은 보합을 제외한 조건부 확률이다. 실제 당일 시가나 분봉은 개장 전 입력에 포함하지 않는다.
- 입력은 SPY·나스닥 종합·필라델피아 반도체지수의 직전 미국장 수익률과 한국의 1·5거래일 수익률이다.
- 15분 연구 검증은 종목별 26~28거래일이다. 두 목표의 확률은 연구 결과로 취급한다.

## 실행

시장 미시구조 스크립트 폴더에서 `requirements-us-kr-preopen.txt`를 설치한 뒤 실행한다. 대상 거래일의 08:30 KST까지 최신 한국·미국 정규장 가격을 조회해 지정한 파일에 쓴다.

```bash
python kr_intraday_direction_engine.py predict --live --target YYYY-MM-DD --output /tmp/kr-intraday-forecast.json
```

과거 재현에는 `--live` 대신 `--prices-dir`과 시간대가 포함된 `--as-of`를 지정한다. `--live`는 수집이 끝난 후 실제 시계를 확인한다. 결과는 공개 여부를 입증하지 않는다.

재학습은 `train --prices-dir ... --opening-labels ... --through YYYY-MM-DD --model <새 파일>`로 수행한다. 가격 파일은 `codex_regime_{kospi,samsung,hynix,spy,nasdaq,sox}_1d.json` 형식이다. 개장 라벨은 거래일과 자산 ID, 실제 정규장 개장·첫 봉 종료 시각, 시가와 첫 봉 종가를 기록한 `rows` 배열이다. 배포 채택 전에 실제 첫 15분 관측과 개장 전 JSON을 날짜별로 짝지어 채점한다.
