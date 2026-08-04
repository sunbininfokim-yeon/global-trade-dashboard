# Namoi–Gwydir 면화 면적 모델 결론

작성일: 2026-08-04
상태: 실험 단계 · 사이트에는 저신뢰도/연구 결과로만 표시

## 결론

NSW Namoi–Gwydir 유역을 호주 면화 파일럿 지역으로 유지하는 판단은 합리적이다.

- ABARES에서 Gwydir·Namoi 면화 `Area_watered` 라벨을 2006–2020년 각각 확보할 수 있다.
- 총 30개 유역×연도 행이며 면적 라벨 결측은 없다.
- 2011–2018년은 ABS 단위자료 기반이고, 나머지는 ABS NRM 자료를 유역으로 배분한 값이다.
- 면화 관개면적과 같은 해 면화 물 사용량의 상관계수는 Gwydir 0.942, Namoi 0.920으로 물-면적 연결은 강하다.
- 그러나 실제 물 사용량은 파종 후 관측되므로 사전 면적예측 변수로 사용하면 데이터 누수가 된다.

## 첫 백테스트 판정

2012–2020년 rolling-origin 검증에서 전년도 면적 유지 기준의 MAE는 11,125ha, WAPE는 36.6%였다.

시즌 시작 carryover와 전년 강수·물가격·물사용을 사용한 초기 물 모델은 MAE 14,595ha, WAPE 48.0%로 기준을 이기지 못했다. 최종 연간 배정률과 같은 사후 정보를 포함한 설명용 모델도 기준보다 낮았다.

따라서 현재 결과는 다음처럼 표시해야 한다.

- 면적 라벨 확보: **성공**
- 물-면적 관계 확인: **성공**
- 사전 면적예측 성능: **미통과**
- 운영 예측/사이트 숫자 제공: **보류**
- 신뢰도: **낮음·연구 단계**

## 다음 단계

1. 파종 전 고정일 기준 NSW 물 배정률·저수량·carryover 자료를 사용한다.
2. GEE에서 Namoi/Gwydir 경계를 맞춘 Landsat·Sentinel 면화 면적 마스크를 독립적으로 만든다.
3. 관개면적과 건조지 면적을 분리한다.
4. 면적 → 실제 증발산/수분 스트레스 → 단수 → 생산량 순으로 분리 모델링한다.

보리·카놀라 등 다른 작물로 전환하는 우선순위 5번은 사용자 승인 전까지 실행하지 않는다.

## 출처

- ABARES MDB Water Market Catchment Dataset 2021: https://www.agriculture.gov.au/abares/research-topics/water/mdb-water-market-dataset
- Cotton Australia Annual Reports: https://cottonaustralia.com.au/annual-reports
