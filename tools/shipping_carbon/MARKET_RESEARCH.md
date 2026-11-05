# 기후금융 화면의 시장 구조와 데이터 범위

조사·확인 기준: 2026-11-04. 아래 상품은 시장 구조의 사례이며, IBK투자증권의 실제 취급 상품·운용 한도·포지션을 뜻하지 않는다.

## 제품 구성 판단

첫 화면은 탄소시장으로 둔다. 앞선 시안에서 날씨·보험이 첫 화면이었던 것은 디자인 선택이며 시장 규모를 비교한 결론이 아니었다. 이번 조사에서도 기후금융 전체의 시장점유율을 산정하지 않았다.

- 탄소시장: 규제 배출권의 조달·거래·자금 위험. EUA·KAU와 프로젝트별 자발적 크레딧은 분리한다.
- 날씨 파생·보험: 고객의 판매량·발전량·생산량 등 물량 위험을 날씨 지수 계약으로 이전하는 전문 영역.
- 농산물 수급·작황: 독립 상품명이 아니라, 원자재 공급·현금흐름·손실을 분석하는 입력. 보험·가격 헤지·신용 분석으로 연결할 수 있으나 각각 검증이 필요하다.

## 1. 날씨 파생은 실제로 어떤 거래인가

[CME Weather Products](https://www.cmegroup.com/markets/weather)는 도시·기간별 기온 지수 선물·옵션, 거래 채널, 브로커, 만기별 OI·증거금 확인 경로를 제공한다. [CME의 거래 구조 설명](https://www.cmegroup.com/openmarkets/energy/2024/Weather-Derivatives-Grow-as-Risks-Intensify.html)은 유틸리티의 물량 위험과 HDD/CDD 블록 거래·ClearPort 이용을 설명한다. 거래 화면에 모든 지수의 연속적인 유동 호가가 존재한다고 전제하면 안 된다.

### 기온 지수의 예

[CME 기온 지수 교육자료](https://www.cmegroup.com/education/lessons/overview-of-weather-markets): 미국 도시의 일별 HDD는 max(65°F − 일평균기온, 0), CDD는 max(일평균기온 − 65°F, 0)를 기간 합산한다. 미국 계약의 단위는 지수당 USD 20이다. 다른 도시·상품의 단위와 기준은 계약 규격을 별도로 확인해야 한다. CAT는 기간별 일평균기온의 합이다.

선물의 최종 지수 기반 계약가치와 거래 손익은 다르다. 매수자의 손익은 진입가격·정산가격 차이와 계약 수량을 반영한다. 옵션은 행사가격·방향·승수·한도·프리미엄이 추가된다. 강수 Put 예시 지급식은 min(한도, max(기준 강수−관측 강수, 0)×단위 지급액)으로 설계할 수 있으나, 이것을 실제 상장상품 규격 또는 보험료로 표시하지 않는다.

### 장외·보험과의 관계

[Munich Re Weather Derivatives](https://www.munichre.com/en/solutions/for-industry-clients/energy-weather.item-93c5adf711b4474ca826c65d4fc3621a.html)는 맞춤 지수 계약, ISDA 계약, 제3자 정산 자료와 기온·강수·풍력·일사량 관련 구조를 소개한다. 고객 노출에 맞춘 OTC 계약과 거래소 표준 계약의 차이를 구분해야 한다. 지수형 구조는 보험 형태로도 구성될 수 있지만, 파생상품과 보험의 법적 분류·취급 요건을 계약 형식이나 지급식만으로 판단하지 않는다.

[IFC 보험 설명](https://www.ifc.org/en/what-we-do/sector-expertise/financial-institutions/financial-inclusion/insurance)은 지수와 개별 농가의 실제 손실이 맞지 않는 베이시스 리스크를 설명한다. 지역 관측지점의 차이와 부적절한 계약 설계가 원인이 될 수 있다. 보험과 파생을 모두 ‘실제 손실을 완전히 보상하는 상품’으로 표현하지 않는다.

### 금융사의 업무 흐름

1. 고객의 기상 민감도: 매출·판매량·발전량·수확량과 지수의 관계, 기간·지리적 노출을 추정.
2. 계약: 관측소 또는 격자, 지수, 정산 제공자, 기간, 승수, strike, cap, 통화, 정정·결측 처리 조건 확정.
3. 가격 제안: 과거 자료·기후 추세·예보 분포·시장 가격을 비교. 기대 지급액과 고객에게 제시할 프리미엄은 구분.
4. 포지션: 도시·월·지수별 민감도와 잔여 지수 분포를 재평가. 고객 노출과 표준 상품 사이의 베이시스를 남긴다.
5. 현금·신용: 청산 또는 양자간 담보, IM/VM, 유동성, 상계 가능 범위와 거래상대 위험 관리.
6. 정산: 계약상 자료원의 확정 지수로 지급하고, 실제 고객 손실과 헤지 결과를 비교.

이는 화면을 위한 업무 분해이며 실제 기관의 프로세스나 승인 체계를 확인한 것은 아니다.

## 2. ‘이상한 데이터’와 흑점의 위치

일반적인 계약 지수·노출에는 기온, 강수, 풍속, 일사량이 직접 연결된다. 보조 예측 변수로 해수면온도·ENSO, 토양수분 등을 검토할 수 있지만 지역·계절별 과거 재예측 검증 없이 매매 신호로 채택하지 않는다. [NOAA CPC ENSO](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml)는 해양·대기 상태와 확률 전망의 공식 경로다. [ECMWF 계절 예측](https://www.ecmwf.int/en/forecasts/documentation-and-support/seasonal)과 [C3S 안내](https://confluence.ecmwf.int/display/CKB/Seasonal+forecasts+and+the+Copernicus+Climate+Change+Service)에서 예보·과거 재예측 자료와 검증 방법을 확인한다. 현재 ENSO 수치를 이 도구에 자동 연결한 것은 아니다.

[NOAA 우주기상 영향](https://www.spaceweather.gov/impacts)은 태양 플레어, 고에너지 입자, 코로나 질량방출이 무선통신·위성·전력망·항법에 주는 영향을 설명한다. 흑점·Kp 등의 우주기상 자료를 검토할 수 있는 영역은 해당 기술·시설의 실제 운영 손실 노출이다. 이번 조사에서 흑점 자체를 기초로 하는 일반적인 상장 날씨 옵션이나, 흑점으로 EUA·곡물 수익률을 예측하는 검증된 실무 모형은 확인하지 못했다. 그래서 기본 탄소·날씨 매매 신호에 넣지 않는다.

## 3. 농업 작황의 실존 활용

[USDA Crop Progress](https://www.nass.usda.gov/Publications/National_Crop_Progress/)는 생육·작황·토양수분 등 공식 자료의 경로를 제공한다. 곡물 분석에서는 작황으로 단수·생산량 시나리오를 만들고 면적·재고·무역·수요와 연결한다. 단수 감소가 곧 동일 비율의 선물가격 상승이라는 뜻은 아니다.

[Munich Re 농업 공급망 솔루션](https://www.munichre.com/en/solutions/for-industry-clients/protection-against-risks-in-the-agricultural-supply-chain.item-23300f839cadad497538c08cdc0a6778.html)은 지역 수확량 지수(AYI), 악천후 지수(AWI), 모형 단수 지수(MYI), 실제 생산량 기반 지수를 소개한다. 따라서 작황·생산량 위험의 이전 구조는 실존한다. 공급자 자료에 표시된 효과·수익·베이시스 축소 홍보 수치는 우리 모형의 검증 결과로 사용하지 않는다.

우리 저장소의 국가별 작황 예측은 연구 입력으로 검토할 수 있다. 그러나 관측 기상을 미래 예보로 보거나, 자체 모형의 예측값을 보험 정산 지수로 채택하거나, 기존 예측 오차를 보험 지급 확률로 바로 치환하면 안 된다. 시간 순서 외부검증, 추세모형 대비 성능, 확률 보정, 공간 베이시스, 실제 손실 설명력을 먼저 확인해야 한다.

## 4. 탄소시장 화면에 연결한 실제 자료

수집기는 원본 해시·행 번호·관측일·수집 시각을 보존한다. 원본과 시세는 git 제외. 아래 수집 결과는 로컬 파일을 확인한 값이며 운영 사이트·API의 실시간 상태가 아니다.

| 계열 | 확인한 관측 범위 | 최신 관측 |
|---|---|---|
| EEX EUA 경매 | 2026년 성공 경매 189건. 낙찰가·물량·응찰배수·입찰량·입찰자 수 | 2026-11-03 |
| ECB KRW/EUR | 2026년 215건. 참조환율 | 2026-11-03 |
| EEX FEUA gross OI | EUA 선물 11개 월물 | 2026-11-02 |

출처: [EEX 시장자료](https://www.eex.com/en/market-data/market-data-hub/environmentals-data), [EEX 경매 다운로드](https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download), [EEX OI 원본](https://www.eex.com/fileadmin/Global/Upload/EEX_Emissions_Open_Interest.xlsx), [ECB 데이터 API](https://data-api.ecb.europa.eu/service/data/EXR/D.KRW.EUR.SP00.A).

일별 가격선은 같은 날 복수 경매를 물량 가중평균한다. 경매가격과 선물 결제가격·현물 bid/ask를 구분한다. 물량 차트는 경매 공급량이며 선물 거래량이 아니다. OI는 EEX 범위의 공개 gross 수치이며 ICE 전체 시장의 유동성이나 순매수 포지션을 뜻하지 않는다. EEX의 synthetic net OI는 EEX가 가정으로 계산한 별도 척도이므로 gross와 섞지 않는다.

## 5. 주요 변수와 앞으로 필요한 시세

‘주요’는 연구·업무 설계상 우선 확인할 변수라는 의미이며, 모든 데스크가 같은 가중치로 사용한다는 조사 결과는 아니다.

- 가격·유동성: 거래소·월물별 settlement, bid/ask, 거래량, OI, 캘린더 스프레드, 현선물 차이, 옵션 IV·skew. 만기별 동일 관측일을 맞춘다.
- 수급: 경매 공급량·일정·응찰배수, 검증 배출량, 무상할당, TNAC·MSR, 산업·발전 수요. [EU 집행위 MSR](https://climate.ec.europa.eu/areas-action/carbon-markets/eu-emissions-trading-system-eu-ets/market-stability-reserve_en)은 TNAC와 경매 공급의 관계를 설명한다. 개정 제안과 현행 규칙을 구분해야 하며 이 도구에서 법정 공급량을 자동 산출하지 않는다.
- 에너지: TTF 가스·석탄·전력의 단위·지역·인도기간을 맞춘 가격, 발전효율·배출계수와 재생에너지 생산량. 임의의 연료 전환 가격을 생성하지 않는다.
- 거래 위험: 고객 인도 의무, 실물 재고, 선물·옵션 delta, EUR/KRW, IM/VM, 차입·인도 시점, 고객 신용.

[ICE EUA 규격](https://www.ice.com/products/197/eua-futures) 및 [EEX EUA 규격](https://www.eex.com/en/markets/environmentals/eu-ets-spot-futures-options)은 EUA 선물 1 lot = 1,000 EUA를 안내한다. 실제 만기·결제·인도는 거래소·상품별 규격을 확인한다.

현재 ICE/EEX 선물 결제·옵션 IV·에너지 시세는 자동 확보하지 못했다. EEX는 [데이터 상품·구독](https://www.eex.com/en/market-data/market-data-hub/environmentals-data)을 안내한다. 시세 사용권·재배포 범위·API 계약을 확인한 피드를 연결하거나, 권한 있는 원자료를 정해진 CSV로 가져온다. 무료 공개 경매·OI 다운로드만으로 실제 매매 호가·체결·증거금 원장을 대체할 수 없다.

## 6. 이번 구현의 사용 범위

- `/climate`: 경매 시계열·물량·조회·CSV, OI, 출처, 기업 조달·금융사 순가격 노출 계산.
- 월물 CSV: 같은 관측일·거래소·EUA settlement만 수용. 미래일·중복 월물·다른 상품·단위 없는 값·혼합 스냅샷은 거부. 거래량·OI 결측은 null.
- 입력한 시세는 `사용자 제공 · 원천 검증 전`. JSON·CSV의 진위나 사용권을 소프트웨어 검증으로 보증하지 않는다.
- 기업: 부족 실물·참조 예산·정수 lot 헤지·±5 EUR 가격/VM 충격을 분리.
- 금융사: 현물 + 선물 delta − 고객 고정가격 공급 의무. 만기·베이시스·신용·IM을 포함한 전체 위험은 미완성.
- 일별 자금 원장은 기존 `/` 해운 시나리오에서 제공. 이번 확장 화면과 실제 계정 연동·주문·체결·가격 예측·정기 수집은 없음.
- PR 병합·운영 배포는 별도 상태로 남긴다.

## 7. FuelEU 독립 검증과 통합 경제성

`audit_fueleu.py`는 EMSA 공식 2024 v254·2025 v80 원본을 별도 프로세스에서 Claude의 기존 추정 코드로 읽는다. 원문 결측과 원문 0을 구분하고, 필수값 관측·양수 연료/CO₂·항로 범위 정합성·중복 IMO를 점검한다. 원래 크기 대리 필터, 유효입력만의 동일 필터, 크기 필터 없음, 기준 선박 수 ±20%를 비교한다. ±20%는 검증을 위한 감도 조건이며 통계적 신뢰구간이 아니다. 2030·2035는 선대·연료를 고정한 규칙 민감도다.

2026-11-04 확인에서 2025 Full ER은 17,430건이고 검사 필드에 결측·비유한 수는 없었다. 연료·CO₂가 원문 0인 2,070건은 결측이 아니며 수급 계산의 양수 조건에서 제외한다. 항로 범위 정합성 조건에서 추가 1건을 보류했다. 이 엄격한 검증을 적용해도 기존 대리 필터의 수급 합계는 바뀌지 않았다. 따라서 결측을 0으로 취급하는 코드 경로가 이번 원본의 합계를 왜곡했다고 주장하지 않는다. 검증용 가상 입력에서는 누락 N₂O·항로 값이 추정값 또는 0 에너지로 진행되는 경로를 별도로 재현했다.

`combined_finance.py`는 FuelEU 법정 계산을 복제하지 않고 `fueleu_adapter.py`를 통해 `tools/fueleu/engine.py`를 호출한다. 다른 `engine.py` 모듈과 섞이지 않도록 프로세스를 분리하며 구현 해시를 결과에 남긴다.

- 기준 연료의 에너지를 고정하고 바이오 **에너지** 비중을 입력한다. LCV 차이만큼 실제 질량이 바뀐다. 같은 질량 비교가 아니다. 엔진 효율·호환성·조달 가능성은 확인 가정이다.
- ETS 계수·적용 비중·단계비율은 별도 입력이다. FuelEU의 WtW 계수나 GWP를 ETS에 자동 전용하지 않는다. 2026년부터의 ETS 가스 범위 및 바이오 0 계수 적격성은 [EU 집행위 ETS FAQ](https://climate.ec.europa.eu/areas-action/transport-decarbonisation/reducing-emissions-shipping-sector/faq-maritime-transport-eu-emissions-trading-system-ets_en)와 원자료로 확인해야 한다.
- 연료·풀 견적은 사용자 입력이며 풀 견적의 준수연도가 계산 연도와 일치해야 한다. 미계약 잉여는 수익으로 인식하지 않는다. 판매 견적과 계약 조건을 명시적으로 확인한 경우에만 해당 시나리오 수익을 반영한다.
- 화석+풀 매입과 동등 에너지 혼합+잔여 매입의 총 참조비용 및 바이오 인도가격 손익분기를 계산한다. 미준수 부담금을 선택 가능한 저가 전략으로 추천하지 않는다.
- 연료·EUA·풀·수수료 지급과 동일한 고객 수금을 날짜별로 묶고, 이전 음수 현금에 actual/365 이자를 부과한다. 일말 최대 추가자금과 이자를 표시한다. 금융 입력이 부족하면 자금 결과는 held/null이다. 장중 피크·IM/VM·신용한도는 이 비교에 포함하지 않는다.

실제 수급 합계·시세·원본 영수증은 git 제외 `source_data/`에서 확인하고 수집 명령으로 재현한다. 기존 FuelEU 파일과 운영 UI·배포·자동 수집은 변경하지 않는다.
