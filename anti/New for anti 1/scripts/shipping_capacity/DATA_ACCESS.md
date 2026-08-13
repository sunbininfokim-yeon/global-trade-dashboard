# Shipping data access and keys

## 현재 키 없이 연결됨

- IMF PortWatch ArcGIS REST: 초크포인트별 일일 선종 추정 교역량(metric tonnes). 730일 ML 창과 2019년 이후 전체 역사 사건 보정 창을 분리해 사용합니다. `capacity_*`는 관측 DWT가 아닙니다.
- World Bank `IS.SHP.GOOD.TU`: 국가별 컨테이너 항만 처리량 TEU.
- IMO·EU 공식 문서: CII/EEXI, EU ETS, FuelEU 규제 사실.
- UNCTAD 공개 데이터·문서: 선대 기준과 연결성 보조지표.

## 무료 키로 연결됨

- `COMTRADE_SUBSCRIPTION_KEY`: UN Comtrade 2024 연간 bilateral `netWgt` 수집. 로컬 키는 코드·JSON에 저장하지 않으며, GitHub 자동화에는 같은 이름의 repository secret으로 별도 등록해야 합니다.
- Water 운송수단이 보고된 셀을 우선하고 없을 때만 전체 운송수단을 폴백합니다. 컨테이너 HS2 중량 공백은 대표 HS4 표본의 kg/USD를 넓은 제조업 교역액에 확장하며 35% 입력 불확실성을 표시합니다.

## 무료 키만으로 해결되지 않는 영역

- 실시간 개별 선박 AIS, IMO 번호별 위치·선종·적재 상태·보험 상태.
- Clarksons 선대·오더북, Baltic Exchange 세부 운임 원자료 등 라이선스 데이터.

키나 유료 데이터가 없을 때는 공식 집계 관측과 명시적 시나리오를 분리하며, 선박별 사실로 표시하지 않습니다.
