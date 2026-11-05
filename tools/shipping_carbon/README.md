# 해운 탄소금융 로컬 시연 도구

해운사의 배출권 조달 필요량을 계산하고 동일 수량을 공급하는 금융사의 가격헤지·증거금 자금위험을 비교한다. 제품 해운 메뉴와 분리된 로컬 검토 도구이며 운영 배포·주문 실행은 포함하지 않는다.

## 실행

Python 3.9 이상. 저장소 루트에서:

```sh
python3 tools/shipping_carbon/server.py --port 8769 --synthetic
```

http://127.0.0.1:8769 에 접속한다. **기본 화면은 공개 관측자료이며 가상 계약 시나리오는 별도로 연다.** 실데이터를 보려면 위 실행 명령에서 `--synthetic`을 빼고 아래 수집 명령을 먼저 실행한다. 수집 파일이 없으면 미확보로 표시하고 가상 가격으로 자동 대체하지 않는다. `--synthetic`은 테스트 전용 가상 가격 80 EUR/EUA·환율 1,500 KRW/EUR을 명시적으로 사용하는 옵션이다. 서버는 loopback에만 바인딩하고 접속 시 외부 API를 호출하지 않는다.

실제 공개 참고자료를 수집하려면 별도 가상환경에 의존성을 설치한다:

```sh
python3 -m venv tools/shipping_carbon/.venv
tools/shipping_carbon/.venv/bin/pip install -r tools/shipping_carbon/requirements.txt
tools/shipping_carbon/.venv/bin/python tools/shipping_carbon/collect_prices.py --as-of 2026-11-01
tools/shipping_carbon/.venv/bin/python tools/shipping_carbon/collect_mrv.py --year 2025
```

EEX 경매 XLSX와 ECB KRW/EUR 참고환율 API는 개발 시 키 없이 실제 응답을 확인했다. 수집기는 원본 URL·관측일·수집시각·해시를 기록하며 원본과 수집 결과는 git 제외 경로인 `source_data/`에 둔다. `redistribution_status`는 `not_verified`이다. 공개 다운로드 가능 여부와 공개 서비스 재배포 권한은 별개다. 실패 기록은 마지막 성공 snapshot을 덮어쓰지 않는다.

EMSA 공식 앱이 사용하는 공개 `downloadable-files` 목록에서 요청 연도·버전을 확인하고 MRV XLSX를 받는다. Full ERs와 Partial ERs를 합산하거나 같은 선박의 다른 기간을 중복 집계하지 않는다. 선박 IMO·명칭·선종·회사·DoC 발행 표기·CO₂ 총량·ETS 보고 CO₂·연료량을 원본 시트·행과 함께 보존한다. `N/A`·빈칸은 null이며 원문 0은 유지한다. DoC 미발행을 발행·검증 완료로 승격하지 않는다. 2025년 보고량을 2026년 제출 의무로 자동 환산하지 않는다. 원문 `m tonnes`는 metric tonnes이고 million tonnes로 배율 변환하지 않는다.

실데이터 화면은 IMO·이름 검색을 제공하며 HMM 보고서가 있으면 초기 검색을 HMM으로 둔다. 공개되지 않은 배출권 보유량·선물 포지션·증거금·고객 계약·풀링 견적은 미확보로 표시한다. 가상 시나리오 입력으로 이 값을 실제 관측값처럼 채우지 않는다.

## EUA 시장·FuelEU 독립 검증·통합 경제성

`python3 tools/shipping_carbon/server.py --port 8775` 후 <http://127.0.0.1:8775/climate>에서 연다.
기존 `/` 해운 계약 화면과 별도이며 실제 시장자료는 아래 수집 결과를 읽는다.

```sh
tools/shipping_carbon/.venv/bin/python tools/shipping_carbon/collect_prices.py --as-of 2026-11-04
tools/shipping_carbon/.venv/bin/python tools/shipping_carbon/collect_market.py --as-of 2026-11-04
tools/shipping_carbon/.venv/bin/python tools/shipping_carbon/audit_fueleu.py --year 2025 --transport curl
```

- EUA 가격선: 일별 물량 가중 경매가격, 공급 물량, 기간·경매 필터, 최근 응찰배수·입찰자, CSV.
- OI: EEX FEUA 월물별 공개 gross OI. ICE 또는 synthetic net OI로 표시하지 않는다.
- 선물 곡선: 실제 이용권한 있는 결제가격 CSV를 브라우저에서 처리. 동일 관측일·거래소·EUA settlement만 수용한다. 자동 피드는 아직 미연결이다.
- 독립 검증: Claude의 `tools/fueleu/{engine,mrv_supply}.py`를 수정하지 않고 별도 프로세스에서 재사용한다. 필드 커버리지·0·중복·양수/범위 조건과 선박 크기 대리 필터 감도를 비교한다.
- 통합 경제성: **동등 에너지**의 화석+풀 매입 / 혼합+잔여 매입. ETS 계수·두 제도 범위·연료/풀 가격은 별도 사용자 입력이며, FuelEU WtW 계수를 ETS에 자동 전용하지 않는다. 실제 가스·바이오 인증·기술적 호환은 확인 가정이다.
- 미계약 잉여 가치는 수익 미인식. 연료·EUA·풀·수수료 지급과 고객 수금을 날짜별로 묶어 actual/365 차입비용·일말 최대 추가자금을 계산한다. 자금 필수값 누락은 held/null이다. IM/VM은 기존 해운 계약 도구에서 별도 검토한다.
- 가정 예제 버튼은 가상 연료/풀 가격·계수·현금흐름을 입력하며 실제 고객 포지션이 아니다. EUA만 수집된 공개 경매 참조값이다.
- `fueleu_adapter.py`는 같은 이름의 두 `engine.py`가 섞이지 않도록 프로세스를 분리한다. 결과에는 FuelEU 구현 SHA256이 남는다. Python 실행 환경에 openpyxl이 있어야 MRV 감사를 실행할 수 있다.

감사 수집이 느리면 공식 파일 다운로드를 먼저 완료하고, 저장한 공식 `downloadable-files` 응답과
`--listing-file path.json --local-file 2024=official2024.xlsx --local-file 2025=official2025.xlsx`를 명시할 수 있다.
완료 전 `.partial` 다운로드는 거부한다. 로컬 파일의 버전 표기는 목록 기반이며 원문 해시를 별도 보존한다.
네트워크 오류는 기존 감사 결과를 대체하지 않는다.

2026-11-04 로컬 원본 확인: 경매 189건·환율 215건(최신 11/03), EEX OI 11개 월물(11/02),
MRV 2024 v254·2025 v80. 2025 Full ER 17,430건에서 검사 필드 결측은 0이며, 원문 0을 결측으로 분류하지 않는다.
엄격한 유효입력 조건을 적용해도 현재 대리 필터의 수급 합계는 동일했다.
실제 수급 감도 결과와 원본·시세·캡처는 `source_data/`에만 두고 git에 포함하지 않는다.
시장 조사·계산 경계·공식 근거는 [MARKET_RESEARCH.md](MARKET_RESEARCH.md)에 있다.

`/api/market`는 선박 보고서 전체를 싣지 않는 시장 요약 API다. `/api/combined`는 로컬 계산 API이며
운영 Worker·사이트 메뉴·정기 수집을 활성화하지 않는다.

## 계산과 두 관점

- 해운사: 가상 배출량에 입력 항로비중·단계비율을 적용한다. 이미 범위 조정된 입력에는 항로비중을 다시 적용하지 않는다. 현재 배정 가능량과 기한 내 인도 예정량을 구분하고 조달 부족량·EUR/KRW 참고 예산·헤지 후 비용 변화를 계산한다.
- 금융사: 고객 공급 수량을 해운사 조달 부족량과 연결한다. 자기계정과 중개를 구분하고 선물 lot을 EUA로 환산해 만기별 델타·고객/선물 가격충격 손익·인도기한 차이를 보여준다. 공통 충격 외에 선물 추가 충격을 입력할 수 있으며 합산 델타가 0이어도 월물 움직임 차이에 따른 손익이 남는다. 미헤지·50%·100% 목표의 순손익과 VM 유출을 나란히 비교한다. 계약 수 올림에 따른 잔여 노출도 표시한다.
- 증거금: 가격충격 후 복귀/유지의 VM 경로를 계산한다. 선물가격은 경매가로 대체하지 않는다. 평가손익과 VM 현금을 중복 합산하지 않는다.
- 자금 일정: 초기 증거금 납입·반환, VM, 선물 실물 인수대금, 보충 실물 매입, 고객 고정가격 수금, 수수료와 차입비용을 날짜별로 연결한다. 입력 현금 여유를 소진한 뒤 음수 일말 잔액을 추가 차입으로 가정한다. 이자는 실제 달력일/365 기준이며 이전 음수 잔액에 다음 이벤트일까지 부과한다. 같은 날짜 이벤트는 일말 합산하므로 장중 자금 피크를 뜻하지 않는다.
- 실물 공급: 고객 인도일보다 늦게 받는 선물은 해당 공급에 배정하지 않는다. 보충가격 미입력 시 전체 자금 결과를 미확인으로 남기고, 늦게 받는 선물 물량은 잔여 재고로 표시한다. IM·고객 공급가격 등 필수 현금 입력이 없으면 전체 최대자금·기여이익을 null로 유지한다.
- 결과 저장: 입력·가정·가격 출처·계산 결과를 브라우저에서 JSON으로 다운로드한다. 오류 또는 계산 진행 중에는 저장을 비활성화한다.
- FuelEU: 사전 계산된 집약도·에너지의 단순 잔액과 가정 풀링 견적 비용만 계산한다. 법정 부담금·연료계수·최적전략은 현행 부속서 검토 전까지 보류한다. 이 잔액은 EUA가 아니다.

`engine.py`는 네트워크 없는 Decimal 계산 모듈이고 `server.py`의 `/api/calculate`가 동일 결과 객체를 두 화면에 전달한다. `acceptance_cases.json`은 독립 기대값을 갖는 합성 사례다. 누락 가격은 0이 아닌 null이며 잘못된 입력 시 화면의 이전 계산 결과를 지운다.

가상 시나리오에는 5천/5만/20만 EUA 거래 규모 가안을 적용할 수 있다. 이는 회사 전체 운용규모가 아니며 선사·금융사 실제 포지션을 대체하지 않는다. 참고 MRV 분포는 실데이터에서 동적으로 계산하고, 포지션·IM·현금 여유는 명시된 가정으로 구분한다. 상세 가정과 해운 외 탄소금융 확장 제안은 [CARBON_FINANCE_PROPOSAL.md](CARBON_FINANCE_PROPOSAL.md)에 있다. `preset_id`는 사용자가 선택한 시작 템플릿이며 이후 입력을 수정할 수 있다.

`funding.py`는 단일 고객 고정가격 공급·선물 매수 계약의 날짜별 자금 모듈이다. 선물 VM과 마지막 결제가격 기준 실물 인수대금을 함께 반영해 같은 비용을 이중 계산하지 않는다. 완전 매칭·기한 내 인도일 때만 공급 차액에서 수수료·가정 차입비용을 차감한 기여이익을 표시한다. 잔여 재고가 있는 경우 확정 이익으로 평가하지 않는다. 기준일+1일 충격, +2일 복귀는 가상 경로이며 실제 거래소 일정이 아니다.

자금 일정을 보려면 금융사 관점에서 초기 증거금(예: 가상 250,000 EUR)을 입력한다. 고객 수금일을 분석 기준일로 바꾸면 선지급, 인도 이후로 바꾸면 후지급의 자금 차이를 비교할 수 있다. 이는 전략 추천이 아닌 동일 가정의 비교다.

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

이미 Chrome이 설치되어 있으면 브라우저 설치 대신 `PW_CHANNEL=chrome npm run test:browser`를 사용할 수 있다. `CARBON_BASE_URL`로 테스트 서버 주소를 바꿀 수 있다. 실제 수집 파일로 실행한 서버는 `PW_CHANNEL=chrome node observed_check.cjs`로 별도 검증한다(기본 8771 포트). 캡처는 git 제외 `source_data/`에 저장한다. Python 단위 테스트는 53개이며 설계 산술 검산은 별도 16개다.

시장·통합 계산 검증:

```sh
node --test tools/shipping_carbon/test_market.mjs
PW_CHANNEL=chrome CARBON_BASE_URL=http://127.0.0.1:8775 node tools/shipping_carbon/market_check.cjs
```

브라우저 검증은 실제 로컬 관측값을 읽고 가격·공급·OI, 필터, 두 관점, CSV 거부, 동등 에너지 통합 계산,
감사 결과, 입력 변경 후 이전 결과/저장 무효화, 메뉴별 320px 가로 넘침을 확인한다.

## 법령·자료 근거와 제한

- [EU ETS 해운 공식 FAQ](https://climate.ec.europa.eu/areas-action/transport-decarbonisation/reducing-emissions-shipping-sector/faq-maritime-transport-eu-emissions-trading-system-ets_en): 적용 범위·제출비율·가스·EUA 제출 설명.
- [FuelEU 공식 Q&A](https://transport.ec.europa.eu/transport-modes/maritime/decarbonising-maritime-transport-fueleu-maritime/questions-and-answers-regulation-eu-20231805-use-renewable-and-low-carbon-fuels-maritime-transport_en): 잔액·유연성 수단·풀링 설명. Q&A와 법령 원문은 구별한다.
- [Regulation (EU) 2023/1805](https://eur-lex.europa.eu/eli/reg/2023/1805): 현행 부속서 직접 대조 미완료. 법정 penalty 계산 보류.
- [EEX 공개 경매 자료](https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download), [ECB API 예제](https://data.ecb.europa.eu/help/api/data-examples): 참고자료 수집 경로.
- [ICE EUA 선물 명세](https://www.ice.com/products/197/EUA-Future): 계약단위·호가·실물인도. 예제의 날짜·월물 입력은 실제 거래소 인도일 조회 결과가 아니다.

이 도구는 법적 적용범위 자동판정·법정 배출량 검증·실거래 손익평가 엔진이 아니다. 적용 대상·가스 환산·면제·예외·실제 인도/청산 일정과 법령 개정은 별도 대조가 필요하다. 현재 화면은 2026 배출연도 가상 사례다. 관측값은 7일 초과 시 `stale`로 표시하며 이 기준은 내부 표시 정책으로 거래일 캘린더를 대체하지 않는다.

제품 통합 후속: 소유권 규칙에 따라 해운 메뉴 연결, 실제 선물 데이터/라이선스, 복수 계약·분할 수금·담보 계약·거래소 일정 연결, 현행 FuelEU 부속서 대조, 검증된 법령 버전 연결. 현재 자금 계산은 단일 계약 가정이며 세금·부도·신용/자본비용·차입한도·자동 청산을 포함하지 않는다. 이 PR 자체는 자동 수집 스케줄이나 운영 UI를 활성화하지 않는다.
