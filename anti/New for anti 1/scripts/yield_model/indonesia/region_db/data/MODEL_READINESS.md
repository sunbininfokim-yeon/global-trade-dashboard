# 인도네시아 지역 패널 모델 준비도

지역 행 수를 독립 표본으로 세지 않고, 같은 수확연도의 공동 충격을 고려해 **서로 다른 연도 수**로 기후 모델 표본 게이트를 판정했다. 현재 결과는 운영 예측이 아니라 데이터·모델 착수 여부 감사다.

## 작물별 판정

| 작물(목표) | 기간 | 독립 시즌 | 안정 지역 | 완전 기후 지역×년 | 기후 게이트 | 추세 최근 MAPE | 최신 APE | 최종 판정 |
|---|---:|---:|---:|---:|---|---:|---:|---|
| 팜유 (CPO) | 2001–2023 | 23/25 | 30 | 690/690 | stopped_insufficient_independent_seasons | 16.6% | 26.6% | stopped_no_operational_model |
| 커피 (coffee beans) | 2016–2023 | 8/25 | 33 | 264/264 | stopped_insufficient_independent_seasons | — | — | stopped_no_operational_model |
| 고무 (dry rubber) | 2007–2023 | 17/25 | 33 | 561/561 | stopped_insufficient_independent_seasons | 25.0% | 48.4% | stopped_no_operational_model |

- `stable_regions`는 모든 연도에 계속 등장하는 공통 지역 수다. 북칼리만탄 생산량은 2015 GAUL 경계와 맞추기 위해 동칼리만탄에 합쳤다.
- 팜유의 목표는 CPO이며 FAOSTAT의 oil-palm fruit/FFB와 같은 값으로 결합하지 않는다.
- 추세 MAPE와 APE는 사전 지정한 전체기간 로그선형 추세의 전진검증 결과다. 기후 모델 정확도가 아니다.

## 상관관계 진단

| 작물 | 면적–생산량 수준 상관 | 연간 증감률 상관 | 추세제거 생산량 CV |
|---|---:|---:|---:|
| 팜유 | +0.993 | +0.704 | 12.4% |
| 커피 | +0.576 | +0.309 | 3.8% |
| 고무 | +0.774 | +0.672 | 11.9% |

수준 상관이 높아도 생산량 ≈ 재배면적 × 생산성이라는 구조와 공통 시간추세가 만든 결과일 수 있다. 따라서 기후 인과성으로 해석하지 않고, 연간 증감률·추세잔차·전진검증을 별도로 본다.

## 최근 3년 평균 상위 생산지역

- **팜유:** Riau 19.4%, Kalimantan Tengah 17.3%, Kalimantan Barat 11.3%, Sumatera Utara 11.0%, Kalimantan Timur 9.7%
- **커피:** Sumatera Selatan 27.0%, Lampung 14.5%, Sumatera Utara 11.1%, Aceh 9.3%, Bengkulu 7.5%
- **고무:** Sumatera Selatan 28.8%, Sumatera Utara 11.3%, Jambi 10.4%, Riau 8.9%, Kalimantan Barat 7.6%

## 현재 결론

세 작물 모두 기후 조정 모델의 최소 25개 독립 시즌을 충족하지 못한다. 팜유와 고무는 단순 추세도 최근·최신 오차 게이트를 넘었고, 커피는 추세 전진검증 자체에 필요한 연도가 부족하다. 따라서 지역별 모델, 통합 패널 기후 모델, 올해 운영 예측값을 모두 중단 상태로 둔다. 다음 우선순위는 더 오래된 BPS/농업부 생산량 확보, 작물 재배지 마스크, 팜 수령·재식재 및 고무 가격·채취강도 같은 비기후 변수를 추가하는 것이다.
