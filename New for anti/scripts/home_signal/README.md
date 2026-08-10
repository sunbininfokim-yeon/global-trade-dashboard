# 홈「오늘 신호」 데이터 계약

이 디렉터리는 `HANDOFF_2026-08-09_home_signal.md` §5의 Codex 범위만 담당한다.
UI, Worker, 배포 워크플로는 수정하지 않는다.

## 산출물

| 파일 | 용도 |
|---|---|
| `public/data/chokepoint_stress_v1.json` | 고정 F2 초크포인트 통합 지수 |
| `public/data/home_signal_series_v1.json` | 순환 A–E 소스·시리즈 매니페스트 |
| `public/data/kospi_risk_slot_v1.json` | 고정 F3의 정직한 placeholder |

싱가포르 VLSFO는 재배포 가능한 대표 공개 가격을 확보하지 못해 에너지 페이지에서
제외한다. 가격이 아닌 MPA 벙커 판매량으로 대체하지도 않는다. 뉴캐슬 연료탄은
FRED의 IMF 호주 석탄 월간 시계열(`PCOALAUUSDM`)을 사용한다. IMF 기술 문서상
원자료 규격은 Argus Newcastle 6000 kcal/kg NAR FOB다.

## 초크포인트 통합

```bash
cd "New for anti"
python3 scripts/home_signal/build_chokepoint_stress.py
```

기존 `shipping_capacity_v1.json`의
`chokepoints_live.*.metrics.all.change_pct`를 산술평균한다. 음수는 최근 7일
capacity가 직전 28일 평균보다 낮다는 뜻이다. 폐쇄 확률이나 실제 폐쇄율이 아니다.
`as_of`는 구성요소 중 가장 오래된 날짜를 써서 혼합 시점 자료의 신선도를 과장하지 않는다.

## 검증

```bash
cd "New for anti/scripts/home_signal"
python3 -m unittest discover -s tests -v
python3 validate_outputs.py
```

`validate_outputs.py`는 `jsonschema`가 설치돼 있으면 세 공개 JSON을 각 스키마로
검사하고, 없으면 표준 라이브러리 기반 핵심 계약 검사를 수행한다.

## Claude 바인딩 메모

- F2: `chokepoint_stress_v1.json`의 `index_pct`, `worst_id`,
  `worst_change_pct`, `as_of`
- A–E: 매니페스트의 `source`, `series_id`, `route`, `availability`
- F3: `status=pending_derivatives`이면 `display_ko=분석 예정`
- `pending_*` 슬롯에는 값 필드를 만들지 않고, 0 또는 보합으로 표시하지 않는다.
