# 한국 반도체 마감 → 미국 반도체 방향 연구

삼성전자와 SK하이닉스의 야간 갭·정규장 수익률에서 각각 코스피의 같은 구간 수익률을 뺀 값을 사용한다. 한국과 미국이 모두 열리는 현지 달력상의 같은 날짜만 예측한다. 한국 마감 뒤부터 미국 정규장 개장 전까지가 추론 시간이다. Yahoo 일봉은 한국 종목의 원주와 미국 상장 종목의 분할 반영 가격을 사용한다. 배당을 제외한 가격 방향이며 보합은 해당 목표의 학습·채점에서 제외한다.

## 비교와 판정

2016년부터 2026-11-20까지 매 분기 이전 자료로만 표준화·로지스틱 학습을 진행했다. 미국 전일 나스닥 종합·SOX·해당 종목 수익률과 직전 20일 변동성에 당일 코스피 갭·장중 수익률을 더한 기준과, 여기에 두 종목의 상대 수익률을 추가한 모델을 같은 날짜에서 비교했다. 5개 대상 × 3개 목표의 Brier 개선에 Newey–West 10시차와 단측 Holm 보정을 적용했다. 각 모델의 표본·Brier·양방향 재현율·보정 p는 고정 모델의 validation에 있다.

- 마이크론 시가 방향의 Brier는 0.2235에서 0.2184로 개선됐다. 종가의 전일 종가 대비 방향은 0.2419에서 0.2382로 개선됐다. 시가 이후 종가 방향의 개선은 확인되지 않았다.
- SOX·NVDA·AMD·AVGO의 개별 종목 추가 효과는 5% 다중검정 기준을 통과하지 않았다. 세 목표는 각각 전일 종가→시가, 시가→종가, 전일 종가→종가다.
- 마이크론 시가 상승·하락 재현율은 각각 82.7%, 45.2%다. 발생률을 감안한 양방향 검증이며 모든 하락을 잘 포착하는 모델로 해석할 수 없다.
- 보조 실험은 나스닥100 선물 NQ=F의 전 미국 종가 시각→한국 개장 전, 한국장 중 변화를 추가한다. 시간봉은 시작 시각에서 1시간을 더한 종가 시각으로 처리하며 한국 정규 마감이 15:30이면 15:00까지의 완결 봉을 쓴다. 공통 검증 261거래일에서 마이크론 시가 개선폭 0.0076의 95% 구간은 −0.0057~0.0208이다. 한국 가격이 미국 주가를 움직였다는 인과성은 식별되지 않는다. 이 선물 입력은 민감도 분석에만 쓰였다.
- 한국 지수는 두 종목을 구성 종목으로 포함한다. 장중 실적 뉴스, 환율, 미국 시간외 가격 등 공동 요인은 남아 있다. SOX 시가는 Yahoo 지수 일봉의 개장 관측값이다. 이 구간의 평가는 과거 재현이며 신규 기간 실제 발행 실적은 추후 축적 대상이다.

## 사용

`New for anti/scripts/market_microstructure`에서 `requirements-us-kr-preopen.txt` 의존성을 사용한다. 가격 폴더는 Yahoo chart 원문 1d JSON이며 파일 이름은 kospi, samsung, hynix, nasdaq, sox, mu, nvda, amd, avgo 각각에 .json을 붙인다. 미국 입력은 목표일 전 거래일까지 읽는다. 출력은 0~1 단위의 up/down과 한국 개별 종목의 추가 검증 여부를 담는다.

```sh
python kr_to_us_semiconductor.py predict --date YYYY-MM-DD --output new-forecast.json
python kr_to_us_semiconductor.py replay --prices snapshots --date 2026-11-24 \
  --as-of 2026-11-24T16:00:00+09:00 --output new-replay.json
python kr_to_us_semiconductor.py train --prices snapshots --date 2026-11-20 \
  --model new-model.json --output new-oos.csv
python research_kr_to_us_futures_control.py --prices snapshots --hourly nq-hourly.json \
  --through 2026-11-20 --output new-nq-check.json
```

predict는 실제 시각에 최신 가격을 내려받고, replay는 사후 재현 표시를 남긴다. 결과 경로는 매 발행 시점 새 파일이어야 한다. 실행기와 연구 아티팩트는 별도로 사용하며 배포와 정기 발행 연결은 검토 후 결정한다.
