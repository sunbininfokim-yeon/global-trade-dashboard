# Mekong WS 성단위 패널 — 유의성 판단

**역할:** 기후→단수 학습을 ops에서 버린 **근거 메모**.  
Ops 제품은 수율 포인트가 아니라 [`risk/`](risk/) **기후 리스크 모니터**.

> 이 문서의 skill / p-value는 “왜 yield를 안 파는지” 설명용이다.  
> 리스크 JSON에 skill·추세 우위를 **다시 넣지 않는다**.

## 1. 패널 커버리지

- 출처: [mtnongnghiep.com trồng trọt](https://mtnongnghiep.com/index.php/du-lieu-trong-trot/) provincial Đông Xuân (GSO-style). GSO V0617 API 미노출 · 연감 PDF 자동추출은 이번 세션에서 차단됨.
- 원본 province-years: **103** → QC 통과: **100**
- 연도: 2017–2024 (T=8)
- 성: Mekong 13 (13)

| province | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---| --- | --- | --- | --- | --- | --- | --- | --- |
| An Giang | ok | ok | ok | ok | ok | ok | ok | ok |
| Bac Lieu | ok | ok | ok | ok | ok | ok | ok | ok |
| Ben Tre | ok | ok | ok | drop | ok | ok | ok | ok |
| Ca Mau | drop | — | ok | ok | ok | ok | ok | ok |
| Can Tho | ok | ok | ok | ok | ok | ok | ok | ok |
| Dong Thap | ok | ok | ok | ok | ok | ok | ok | ok |
| Hau Giang | ok | ok | ok | ok | ok | ok | ok | ok |
| Kien Giang | ok | ok | ok | ok | ok | ok | ok | ok |
| Long An | ok | ok | ok | ok | ok | ok | ok | ok |
| Soc Trang | ok | ok | ok | ok | ok | ok | ok | ok |
| Tien Giang | ok | ok | ok | ok | ok | ok | ok | ok |
| Tra Vinh | ok | ok | ok | drop | ok | ok | ok | ok |
| Vinh Long | ok | ok | ok | ok | ok | ok | ok | ok |

`drop` = yield QC 실패 (비현실 수율/오염 셀). `—` = 원천 결측.

## 2. 판정

**현재 데이터로는 불가** — Forward CV skill −24.7%(성 추세 대비 악화), T=8, 이론 부호 일치 4/7. 유일하게 p≈0.001인 `spei4_ws_min`도 부호가 이론과 반대라 기후→수율 ‘유의’ 주장은 불가.

## 3. 주요 통계

| 항목 | 값 |
|---|---|
| FE n (province-years) | 100 |
| N provinces / T years | 13 / 8 |
| Within R² | 0.142 |
| Forward CV n | 52 (years [2021, 2022, 2023, 2024]) |
| RMSE model / province trend | 490.9 / 393.6 kg/ha |
| Skill vs province trend | -24.7% |
| p<0.05 (cluster SE) | spei4_ws_min |
| p<0.10 | spei4_ws_min, heat_days_35_ws |
| 이론 부호 일치 | 4/7 |

### Province FE 계수

| feature | coef | SE (prov cluster) | p≈ | theory | match |
|---|---:|---:|---:|:---:|:---:|
| spei4_ws_min | -0.0389 | 0.0118 | 0.001 | + | ✗ |
| spi_ws | +0.0259 | 0.0336 | 0.442 | + | ✓ |
| oni_lag2 | +0.0105 | 0.0087 | 0.226 | - | ✗ |
| q_upstream_proxy | +0.0132 | 0.0278 | 0.635 | + | ✓ |
| salt_coastal_belt | -0.1197 | 0.1729 | 0.489 | - | ✓ |
| precip_dry_ws | -0.0003 | 0.0003 | 0.309 | + | ✗ |
| heat_days_35_ws | -0.0017 | 0.0009 | 0.060 | - | ✓ |

### Power / 해석 주의

- T=8은 성 FE + 연도 공통충격(ONI, Q-proxy) 분리에 매우 약함.
- Cluster SE는 G=13으로 근사 p-value — 소표본에서 과소/과대 가능.
- 면적 컬럼은 2017–2020 다수 오염 → **수율만** 분석에 사용.
- 지역 집계 모델 skill(−4.6%)과 별개: 성 패널은 이질성 신호 탐색용.

## 4. Ops 결론 (면접·리뷰용 한 줄)

패널이 성 추세를 이기지 못했으므로 **단수 예측을 제품화하지 않는다.**  
동일 드라이버(Q·염분·가뭄·ENSO)는 **프록시 라벨을 붙인 조기경보 리스크**로만 낸다.
상세: `risk/README.md` · 볼트 `메콩_리스크모니터_피벗.md`.

## 5. 연구로만 이어갈 것 (ops 아님)

1. GSO 연감/V0617에서 **2010–2016** Đông Xuân 성 수율 확보 (T≥12–15)
2. Ben Tre·Ca Mau 결측/오염 셀을 성 통계연감으로 보정
3. MRC Tan Chau 유량으로 `q_upstream_proxy` 대체
4. 연도 FE 또는 ENSO 이벤트 케이스 스터디와 병행
5. 면적(식부)은 단수와 **분리** — S1/GEE auth 시 anomaly만 리스크 채널로

