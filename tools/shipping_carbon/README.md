# 해운 탄소금융 로컬 시연 도구

해운사의 배출권 조달 필요량을 계산하고 동일 수량을 공급하는 금융사의 가격헤지·증거금 자금위험을 비교한다. 제품 해운 메뉴와 분리된 로컬 검토 도구이며 운영 배포·주문 실행은 포함하지 않는다.

## 실행

Python 3.9 이상. 저장소 루트에서:

```sh
python3 tools/shipping_carbon/server.py --port 8769 --synthetic
```

http://127.0.0.1:8769 에 접속한다. 기본 샘플은 **가격·환율·배출량·포지션 모두 가상 데이터**이고 화면에 `synthetic`으로 표시한다. 가상 가격 80 EUR/EUA와 환율 1,500 KRW/EUR은 실제 관측값이 아니다. `--synthetic` 없이 실행하면 로컬 수집 성공 파일을 우선 사용하며, 파일이 없으면 가상 샘플로 시작한다. 서버는 loopback에만 바인딩하고 접속 시 외부 API를 호출하지 않는다.

실제 공개 참고자료를 수집하려면 별도 가상환경에 의존성을 설치한다:

```sh
python3 -m venv tools/shipping_carbon/.venv
tools/shipping_carbon/.venv/bin/pip install -r tools/shipping_carbon/requirements.txt
tools/shipping_carbon/.venv/bin/python tools/shipping_carbon/collect_prices.py --as-of 2026-11-01
```

EEX 경매 XLSX와 ECB KRW/EUR 참고환율 API는 개발 시 키 없이 실제 응답을 확인했다. 수집기는 원본 URL·관측일·수집시각·해시를 기록하며 원본과 수집 결과는 git 제외 경로인 `source_data/`에 둔다. `redistribution_status`는 `not_verified`이다. 공개 다운로드 가능 여부와 공개 서비스 재배포 권한은 별개다. 실패 기록은 마지막 성공 snapshot을 덮어쓰지 않는다.

## 계산과 두 관점

- 해운사: 가상 배출량에 입력 항로비중·단계비율을 적용한다. 이미 범위 조정된 입력에는 항로비중을 다시 적용하지 않는다. 현재 배정 가능량과 기한 내 인도 예정량을 구분하고 조달 부족량·EUR/KRW 참고 예산·헤지 후 비용 변화를 계산한다.
- 금융사: 고객 공급 수량을 해운사 조달 부족량과 연결한다. 자기계정과 중개를 구분하고 선물 lot을 EUA로 환산해 만기별 델타·평행 가격충격 손익·인도기한 차이를 보여준다. 선물가격은 독립 가정 입력이고 경매가로 대체하지 않는다.
- 증거금: 가격충격과 원위치 복귀의 3단계 VM 경로를 계산한다. 입력 현금 여유를 차감하며 IM 미입력 시 전체 자금소요는 미확인이다. 실제 인도대금·고객 수금·수수료·담보는 별도 모델링 대상이다. 평가손익과 VM 현금을 중복 합산하지 않는다.
- FuelEU: 사전 계산된 집약도·에너지의 단순 잔액과 가정 풀링 견적 비용만 계산한다. 법정 부담금·연료계수·최적전략은 현행 부속서 검토 전까지 보류한다. 이 잔액은 EUA가 아니다.

`engine.py`는 네트워크 없는 Decimal 계산 모듈이고 `server.py`의 `/api/calculate`가 동일 결과 객체를 두 화면에 전달한다. `acceptance_cases.json`은 독립 기대값을 갖는 합성 사례다. 누락 가격은 0이 아닌 null이며 잘못된 입력 시 화면의 이전 계산 결과를 지운다.

## 검증

```sh
python3 -m unittest discover -s tools/shipping_carbon -p 'test_*.py' -v
python3 tools/shipping_carbon/validate_cases.py
```

브라우저 확인은 `--synthetic --port 8769` 서버에 대해 실행한다:

```sh
cd tools/shipping_carbon
npm install
npx playwright install chromium
npm run test:browser
```

이미 Chrome이 설치되어 있으면 브라우저 설치 대신 `PW_CHANNEL=chrome npm run test:browser`를 사용할 수 있다. `CARBON_BASE_URL`로 테스트 서버 주소를 바꿀 수 있다. 캡처는 git 제외 `source_data/`에 저장한다. 입력 변경·두 관점 전환·가격 미입력·입력 오류·초기화·모바일 가로 넘침을 확인한다.

## 법령·자료 근거와 제한

- [EU ETS 해운 공식 FAQ](https://climate.ec.europa.eu/areas-action/transport-decarbonisation/reducing-emissions-shipping-sector/faq-maritime-transport-eu-emissions-trading-system-ets_en): 적용 범위·제출비율·가스·EUA 제출 설명.
- [FuelEU 공식 Q&A](https://transport.ec.europa.eu/transport-modes/maritime/decarbonising-maritime-transport-fueleu-maritime/questions-and-answers-regulation-eu-20231805-use-renewable-and-low-carbon-fuels-maritime-transport_en): 잔액·유연성 수단·풀링 설명. Q&A와 법령 원문은 구별한다.
- [Regulation (EU) 2023/1805](https://eur-lex.europa.eu/eli/reg/2023/1805): 현행 부속서 직접 대조 미완료. 법정 penalty 계산 보류.
- [EEX 공개 경매 자료](https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download), [ECB API 예제](https://data.ecb.europa.eu/help/api/data-examples): 참고자료 수집 경로.
- [ICE EUA 선물 명세](https://www.ice.com/products/197/EUA-Future): 계약단위·호가·실물인도. 예제의 날짜·월물 입력은 실제 거래소 인도일 조회 결과가 아니다.

이 도구는 법적 적용범위 자동판정·법정 배출량 검증·실거래 손익평가 엔진이 아니다. 적용 대상·가스 환산·면제·예외·실제 인도/청산 일정과 법령 개정은 별도 대조가 필요하다. 현재 화면은 2026 배출연도 가상 사례다. 관측값은 7일 초과 시 `stale`로 표시하며 이 기준은 내부 표시 정책으로 거래일 캘린더를 대체하지 않는다.

제품 통합 후속: 소유권 규칙에 따라 해운 메뉴 연결, 실제 선물 데이터/라이선스, 계약별 인도대금·고객수금·담보 스케줄, 현행 FuelEU 부속서 대조, 검증된 법령 버전 연결. 이 PR 자체는 자동 수집 스케줄이나 운영 UI를 활성화하지 않는다.
