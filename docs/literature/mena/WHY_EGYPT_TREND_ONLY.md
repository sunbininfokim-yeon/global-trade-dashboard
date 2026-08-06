# 왜 Egypt Nile 밀은 기상 모델을 안 쓰는가 (trend-only)

작성: 2026-08-06 · 코드: `scripts/yield_model/mena/`  
측정 (FAOSTAT 1985–2024, forward-chaining): **recent skill vs trend ≈ −41%**, `beats_trend: false`.

## 운영 정책 (이 패키지)

| 지역 | 학습 | 운영 point |
|------|------|------------|
| Morocco / Algeria | Maghreb rainfed Ridge (단순 유지) | trend + weather residual |
| **Egypt Nile** | 동일 골격으로 학습·기록은 함 | **`trend`만** (`operational_mode: trend_only`) |

날씨 Ridge 계수는 artifact에 남기되, skill이 트렌드를 못 이기면 **잔차를 발행하지 않는다**.

## 왜 안 되는가 (요약)

1. **관개 체제** — 국소 강수 ≈ 0. WD는 비 부족이 아니라 ET0(열) 대리에 가깝고, 관개 버퍼가 WD를 깎음. 근권수분 변동이 거의 평탄 → POWER 기상 잔차가 작다. 단수 CV(~14%)도 Maghreb(~37%)보다 낮아 트렌드만으로도 잘 맞는다.

2. **라벨 불일치** — FAOSTAT **전국** Wheat vs Delta+Middle Egypt 점 피처 (`labels_season_imperfect`).

3. **드라이버가 proxy** — `nile_inflow_proxy` = 에티오피아 JJAS 강수 (≠ G-REALM). `salt_proxy` ≠ 필드 EC. 문헌이 강조하는 실측 관개·염분·나일이 아님.

4. **CV** — 선택 모델이 최근 fold에서 최고 트렌드 baseline을 못 이김 → `beats_trend: false`.

## 문헌과의 정합

DSSAT/AquaCrop/JRC는 Egypt를 rainfed yield 모델로 거의 다루지 않는다. 기상-only 실패는 그 서술과 일치. Maghreb만 GSR/SPEI 경로가 맞다.

## 다음에 weather를 켜려면

G-REALM Lake Nasser + (가능하면) CAPMAS 주별 단수로 skill이 트렌드를 이길 때만 승격.
