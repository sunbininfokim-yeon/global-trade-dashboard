# 중남미 바나나 정적 참고·리스크 패널

## 사용 범위

에콰도르·과테말라·코스타리카·온두라스 **수출 캐번디시**에 대해
**예측(point)을 하지 않는다.** FAO·기관 통계와 질병·폭풍·TR4 리스크 메모만
올린다. 서아프리카 코코아 참고패널과 같은 계약
(`forecast_available: false`, `panel_mode: reference`).

농장 면담·미세 생육 관측은 벨트 수출 공급 이야기에 의미가 없어
수집·표시하지 않는다.

## 왜 수량성 forecast가 없는가

문헌에서 송이/박스 예측이 되는 입력은 **주간 YLWS·YLS(블랙 시가토카 병 점수)**
또는 농장 UAV NDVI다. 해당 시계열은 협동조합·CORBANA 등 **비공개**이며,
대표 논문(Olivares et al. 2022) Data Availability도 **"Not applicable"**이다.
확보 시도 로그: `YLWS_ACQUISITION.md`.

## 화면에 올릴 것

1. 제목: `바나나 생산·리스크 참고자료` (예상 생산량 금지)
2. 기관 통계는 **자료연도·정의**(수출 vs 생산, 달력연도)를 항상 붙인다
3. 시가토카 / 허리케인 blowdown(~80 km/h) / TR4 면적 격리는 **서술 리스크**
4. 상승·하락 화살표·신뢰구간·모델 point 없음

기계가 읽는 값: `reference/banana_country_profiles.json`  
생성: `python3 -m latam_banana.build_reference`
