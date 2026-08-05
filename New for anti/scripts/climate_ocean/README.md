# climate_ocean

`public/data/climate_global_v1.json` 의 **해양 신호 3블록**(`enso` · `iod` · `north_atlantic`)을
실관측으로 갱신한다. 나머지 필드(`cities`, `map_temp_anomaly_seed`, `climate_derivatives`,
`continent_temp_anomaly`)는 아직 seed 이며 이 스크립트가 건드리지 않는다.

## 실행

```bash
python3 "New for anti/scripts/climate_ocean/build_ocean_signals.py" --check
```

`--check` 는 계산 결과만 출력하고 파일을 쓰지 않는다. 플래그 없이 실행하면 JSON 을 갱신한다.
표준 라이브러리만 쓰므로 venv 없이 돌아간다.

## 소스

| 필드 | 소스 | 비고 |
|------|------|------|
| `enso` | NOAA CPC `oni.ascii.txt` | 계절별 Niño 3.4 편차, 최근 12개 |
| `iod` | NOAA PSL `dmi.had.long.data` | HadISST 기반 월별 DMI |
| `north_atlantic` | NOAA OISST v2.1 (ERDDAP griddap) | 해역 박스 면적평균 (위도 코사인 가중) |
| `north_atlantic.nao` | NOAA PSL / CPC `nao.data` | 월별 북대서양 진동 |

전부 공개 엔드포인트이며 API 키가 필요 없다.

## 해역 박스

| 이름 | 범위 | 의미 |
|------|------|------|
| `north_atlantic` | 0–60N, 80W–0 | 북대서양 전체. 아열대 난수 포함이라 통상 양의 편차 |
| `subpolar_gyre` | 45–60N, 50–20W | 이른바 warming hole / cold blob 자리 |
| `labrador_sea` | 55–65N, 60–45W | 심층수 형성 해역 (열염순환) |

`cold_blob` 플래그는 **북대서양 전체가 양의 편차인데 아극환류만 음** 인 경우 참이 된다.

## 주의

이 값들은 **관측이지 예측이 아니다.** 해류·AMOC 는 수십 년 스케일이라 시즌 단위
단수(yield) 모델의 피처가 될 수 없다. UI 에서도 예측 인자가 아닌 **배경 컨텍스트**로
라벨링할 것. 실제로 단수 모델에 들어가는 해양 신호는 ONI · DMI · SAM 이다.

## AMOC 수송량 (미구현)

RAPID 26°N 어레이가 `moc_transports.nc` 를 공개하지만 netCDF 파서 의존성이 필요해
이번 범위에서 뺐다. 붙일 경우 `north_atlantic.amoc_sv` 로 추가.
