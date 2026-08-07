#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge Phase-2 panel body strings into locales/{ko,en}.json. Run from repo root."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KO_PATH = ROOT / "locales" / "ko.json"
EN_PATH = ROOT / "locales" / "en.json"

# (key, ko, en) — full paragraphs where app.js concatenates fragments.
PAIRS: list[tuple[str, str, str]] = [
    # --- US region method cards ---
    (
        "us.method.corn_belt.headline",
        "추세수확량 + 기상편차 회귀",
        "Trend yield + weather-anomaly regression",
    ),
    (
        "us.method.corn_belt.note1",
        "추세가 품종·비료·경영 개선을 흡수하고, 기상은 추세로부터의 편차만 설명합니다 (FAO 작황예측 리뷰).",
        "Trend absorbs cultivar, fertilizer, and management gains; weather explains only deviations from trend (FAO crop-forecasting review).",
    ),
    (
        "us.method.corn_belt.note2",
        "고온은 일수 카운트가 아니라 임계 초과분 적산(EDD)으로 넣습니다 — 손상이 비선형이기 때문입니다 (옥수수 −8.2%/°C, 대두 −5.7%/°C).",
        "Heat enters as excess degree-days (EDD) above a threshold, not day counts — damage is nonlinear (corn −8.2%/°C, soybeans −5.7%/°C).",
    ),
    (
        "us.method.corn_belt.note3",
        "VPD로 고온·건조 복합 스트레스를, 파종전 강수(9~6월)로 토양수분 충전을 봅니다.",
        "VPD captures combined heat–drought stress; pre-plant rainfall (Sep–Jun) captures soil-moisture recharge.",
    ),
    (
        "us.method.corn_belt.finding",
        "데이터가 뽑아낸 상위 변수(7월 기온 r=−0.635, 7월 EDD −0.632, VPD −0.536)가 40년 전 논문이 지목한 시기·변수와 그대로 일치했습니다.",
        "Top variables from the data (July temperature r=−0.635, July EDD −0.632, VPD −0.536) match the timing and drivers flagged in papers from 40 years ago.",
    ),
    (
        "us.method.great_plains.headline",
        "추세수확량 + 기상편차 회귀 (겨울밀)",
        "Trend yield + weather-anomaly regression (winter wheat)",
    ),
    (
        "us.method.great_plains.refs",
        "Kansas State (hot-dry-windy) · 대평원 겨울밀 모델링 가이드",
        "Kansas State (hot-dry-windy) · Great Plains winter-wheat modeling guide",
    ),
    (
        "us.method.great_plains.note1",
        "가을 파종 → 월동 → 초여름 수확. 생육창이 해를 넘기므로 전년 9월부터 봅니다.",
        "Fall sow → overwinter → early-summer harvest. The growing window spans years, so we start from prior September.",
    ),
    (
        "us.method.great_plains.note2",
        "반건조 지대라 물이 지배합니다: 봄철 토양수분(r=+0.732), 겨울 토양수분(+0.654), 봄 강수(+0.565).",
        "In this semi-arid belt water dominates: spring soil moisture (r=+0.732), winter soil moisture (+0.654), spring rainfall (+0.565).",
    ),
    (
        "us.method.great_plains.finding",
        "참고 가이드가 강조한 춘화처리·동해·서리 패널티는 신호가 없었습니다 (r=+0.020 / −0.104 / −0.071). 서리 최다 3개년 중 2019년은 오히려 증수라 방향도 엇갈립니다. 공식대로 구현했으나 이 지역·이 기간에서는 지배 요인이 아니었습니다.",
        "Vernalization, winterkill, and frost penalties emphasized in the guide showed no signal (r=+0.020 / −0.104 / −0.071). Among the three frostiest years, 2019 even yielded above trend — signs conflict. Implemented as specified, but not dominant for this region and period.",
    ),
    (
        "us.method.cotton_belt.headline",
        "추세수확량 + 기상편차 회귀 (면화, 파종면적 기준)",
        "Trend yield + weather-anomaly regression (cotton, planted-area basis)",
    ),
    (
        "us.method.cotton_belt.note1",
        "개화~꼬투리 충실기(7~9월) 수분이 꼬투리 수를 결정합니다. 면화는 고온 내성이 높아 EDD 임계를 32°C로 잡았습니다.",
        "Moisture in flowering–boll fill (Jul–Sep) sets boll count. Cotton’s heat tolerance led us to set the EDD threshold at 32°C.",
    ),
    (
        "us.method.cotton_belt.note2",
        "텍사스 하이플레인스는 오갈라라 대수층 관개 의존도가 높아, 파종 전(11~4월) 토양수분 충전이 함께 들어갑니다.",
        "The Texas High Plains lean on Ogallala aquifer irrigation, so pre-plant (Nov–Apr) soil-moisture recharge is included.",
    ),
    (
        "us.method.cotton_belt.finding",
        "수확면적이 아니라 파종면적 기준으로 단수를 계산했습니다. 텍사스 수확포기율이 연도별 4~75%로 요동치는데, 가뭄해에 농민이 망한 밭을 갈아엎으면 살아남은 관개 밭만 측정돼 단수가 오히려 높게 찍힙니다(2022년 포기율 74.5%인데 단수 734 lb/ac로 평년 이상). 파종면적 기준으로 바꾸니 변동계수가 10.0%→37.1%로 커지고 최악 3개년이 2022·2011·2023 — 실제 텍사스 가뭄해와 일치합니다.",
        "Yield (per-area) is computed on planted area, not harvested area. Texas abandonment swings 4–75% by year; in drought years farmers plow under failed fields, so only surviving irrigated fields are measured and yield looks high (2022 abandonment 74.5% yet 734 lb/ac above normal). On planted area, CV rises 10.0%→37.1% and the worst three years are 2022·2011·2023 — matching actual Texas drought years.",
    ),
    (
        "us.method.northern_plains.headline",
        "추세수확량 + 기상편차 회귀 (봄밀, 20년 이동창)",
        "Trend yield + weather-anomaly regression (spring wheat, 20-year moving window)",
    ),
    (
        "us.method.northern_plains.note1",
        "봄 파종 → 늦여름 수확. 생육창이 짧아 개화기가 한여름 폭염과 겹칩니다.",
        "Spring sow → late-summer harvest. The short window puts flowering into midsummer heat.",
    ),
    (
        "us.method.northern_plains.note2",
        "밀은 옥수수보다 고온에 취약해 EDD 임계를 28°C로 낮춰 잡았습니다.",
        "Wheat is more heat-sensitive than corn, so the EDD threshold is set lower at 28°C.",
    ),
    (
        "us.method.northern_plains.finding",
        "고정 계수로는 추세만 쓰는 것보다 나빴습니다(−1.0%). 봄밀이 조기 파종·조기출수 품종으로 7월 더위를 회피하도록 적응해와서, \"고온→감수\" 관계 자체가 약해졌기 때문입니다. 최근 20년만 재적합해 +13.4%로 돌렸습니다 — 다만 여전히 낮습니다.",
        "Fixed coefficients did worse than trend-only (−1.0%). Spring wheat adapted via earlier sowing/heading to dodge July heat, so the heat→loss link itself weakened. Refitting the last 20 years recovers +13.4% — still low.",
    ),
    # --- Brazil non-weather callouts ---
    (
        "br.nonwx.parana_milho",
        "SIDRA는 주별 옥수수를 1기작·2기작 합산 단일 수치로 발표합니다. 파라나는 두 작기가 모두 크고 재배 면적 배분이 대두·옥수수 가격에 따라 해마다 바뀌므로, 이 목표값의 연간 변동 중 일부는 날씨가 아니라 면적 배분 의사결정입니다. 다만 \"옥수수엔 날씨가 안 통한다\"는 뜻은 아닙니다 — 방향은 대두와 같습니다. 같은 지역 탈추세 로그수확량으로 옥수수·대두 상관을 재보면 +0.70이고, 옥수수 자체 기상 피처(VPD_peak −0.52, SPI3_Jan +0.42)도 농학적으로 맞는 방향으로 옥수수 수확량을 움직입니다. 그런데 같은 기상 변수가 옥수수 자기 수확량보다 대두 수확량과 더 강하게 상관됩니다(−0.61, +0.59). 즉 옥수수 목표값엔 진짜 날씨 신호가 있고, 그 위에 비기상 잡음이 얹혀 있는 것이지, 날씨가 이 작물을 안 움직이는 게 아닙니다.",
        "SIDRA publishes state corn as a single figure combining 1st and 2nd crops. In Paraná both crops are large and area mix shifts yearly with soy/corn prices, so part of the target’s year-to-year change is acreage allocation, not weather. That does not mean “weather does not move corn” — the direction matches soy. Detrended log yield correlation of corn vs soy in the same region is +0.70, and corn’s own weather features (VPD_peak −0.52, SPI3_Jan +0.42) move corn yield in agronomically correct directions. Yet those same weather variables correlate more strongly with soy yield than with corn (−0.61, +0.59). So the corn target carries a real weather signal with non-weather noise on top — weather does move this crop.",
    ),
    (
        "br.nonwx.sp_cana",
        "사탕수수는 5~7년에 한 번만 갱신하는 ratoon(그루터기) 작물이라, 특정 해의 수확량은 상당 부분 식재 연차 구성(상파울루 면적 중 1번지기 대 5번지기 비율)에 좌우됩니다. 이는 갱신 투자·품종 교체·제당공장 경제성이 정하는 값이며 어떤 기상 데이터에도 나타나지 않습니다. 이건 이 모델의 한계가 아니라 학계의 정설입니다 — Dias & Sentelhas(2017)가 표준 시뮬레이터 3종(FAO-AZM·DSSAT/CANEGRO·APSIM)을 브라질 상업 포장에 적용했을 때 MAE 29 t/ha 초과, R² 0.54 미만이었고, 원인을 \"경영을 반영하는 계수의 부재\"로 지목했습니다. 그루터기 감퇴 계수(kdec)를 넣자 MAE 13~15 t/ha, R² 0.58~0.72로 개선됐습니다. 기후만으로는 누구도 이 작물을 예측하지 못합니다. 팜유·커피 같은 다른 다년생 작물과는 성격이 다른 문제입니다. 팜유의 다년성은 고정된 생리 시차입니다 — 가뭄이 오면 24개월 뒤 열릴 열매의 성별이 강제로 바뀌므로, 12~24개월 누적 수분적자를 시차로 넣으면 실제로 잡힙니다(업계 표준 관행). 사탕수수를 지배하는 그루터기 연차는 그런 날씨-시차 메커니즘이 아예 없습니다 — 언제 갈아엎어 재식할지의 투자 결정입니다. 문서가 요구한 다년 누적 방식(12~18개월 수분적자, SPI-12)을 이미 넣어봤는데도 날씨만의 기여는 −13.6%로 그대로 마이너스였습니다. 시차를 늘려도 안 됐다는 건, 애초에 빠진 게 \"더 긴 날씨 기억\"이 아니라 \"날씨로 환원 안 되는 변수\"라는 뜻입니다. 경영 대리변수인 lag1조차 표준화 효과가 +0.1%로, 11개 피처 중 가장 약합니다 — 그루터기 연차 대리변수마저 이 정도로 안 움직인다는 게 사탕수수 변동성이 얼마나 안 잡히는지를 보여줍니다.",
        "Sugarcane is a ratoon crop renewed only every 5–7 years, so a given year’s yield largely reflects the age mix (1st-cut vs 5th-cut share of São Paulo area). That is set by renewal investment, variety turnover, and mill economics — nothing in weather data. This is academic consensus, not just our model’s limit — Dias & Sentelhas (2017) applied three standard simulators (FAO-AZM·DSSAT/CANEGRO·APSIM) to Brazilian commercial fields and got MAE >29 t/ha, R² <0.54, blaming “missing coefficients that reflect management.” Adding a ratoon-decline coefficient (kdec) improved MAE to 13–15 t/ha and R² to 0.58–0.72. Nobody forecasts this crop on climate alone. Unlike other perennials such as oil palm or coffee: palm’s multi-year effect is a fixed physiological lag — drought forces sex of fruit opening 24 months later, so 12–24 month cumulative moisture deficit actually works (industry practice). Sugarcane’s ratoon age has no such weather–lag mechanism — it is an investment choice of when to replant. We already tried the doc’s multi-year accumulation (12–18 month moisture deficit, SPI-12); weather-only contribution stayed −13.6%. Longer lags failing means the missing piece is not “longer weather memory” but a variable that does not reduce to weather. Even management proxy lag1 has standardized effect +0.1%, weakest of 11 features — even a ratoon-age proxy barely moves, showing how hard cane variability is to capture.",
    ),
    (
        "br.nonwx.sp_cafe",
        "해걸이(격년결실)는 기상이 아니라 생리 현상입니다. 많이 열린 해에 나무가 소진되면 이듬해는 날씨와 무관하게 적게 열립니다. lag1·lag2가 이 주기를 담고 있고 이 둘이 모델의 최강 피처이므로, 이 모델 성능의 상당 부분은 기후가 아니라 생물학적 기억입니다. lag1·lag2를 빼고 기상 피처만 남기면 스킬이 +1.6%로 줄어듭니다(전체는 +8.6%). 서리·개화기 수분결핍이라는 진짜 기후 메커니즘은 있지만(문서에도 명시, 물리적으로도 잘 알려짐), 주(州) 단위 연간 데이터에서는 해걸이 주기가 그 변동을 압도합니다. \"다년 메모리를 넣었다\"가 자동으로 \"날씨가 이긴다\"를 보장하진 않는다는 걸 이 작물이 가장 명확하게 보여줍니다.",
        "Biennial bearing is physiology, not weather. After a heavy crop year the tree is depleted and yields less the next year regardless of weather. lag1·lag2 carry that cycle and are the model’s strongest features, so much of the skill is biological memory, not climate. Dropping lag1·lag2 and keeping weather features only cuts skill to +1.6% (full model +8.6%). Real climate mechanisms exist (frost, flowering moisture stress — stated in the doc and well known physically), but at state–annual scale the biennial cycle dominates. This crop most clearly shows that “we added multi-year memory” does not automatically mean “weather wins.”",
    ),
    (
        "br.nonwx.sp_laranja",
        "이 문서는 첫 문단부터 \"이 시장은 기후가 아닌 감귤 녹화병(HLB)에 의해 붕괴되고 있다\"고 명시하며, 처방된 모델링도 드론 CNN과 공간 확산 모델이지 기상 모델이 아닙니다. 데이터도 같은 말을 합니다 — HLB는 나무를 죽이지 헥타르당 수확량을 낮추지 않습니다. 상파울루 오렌지 재배면적은 1991년 정점 대비 55% 감소(789,329→354,562 ha)했는데, 살아남은 면적의 단수는 2005년 이후 오히려 35% 상승했습니다. 감염목을 뽑아내면 남은 과수원이 더 젊고 관리가 좋기 때문입니다. 따라서 이 kg/ha 수치는 산업이 축소되는 중에도 우상향으로 보입니다. 반드시 재배면적과 함께 읽어야 하며, 단독으로 해석하면 안 됩니다.",
        "The document states from paragraph one that “this market is collapsing from citrus greening (HLB), not climate,” and prescribed modeling is drone CNN and spatial spread models — not weather models. Data say the same — HLB kills trees; it does not lower yield per hectare. São Paulo orange area fell 55% from the 1991 peak (789,329→354,562 ha), yet yield (per-area) on surviving area rose ~35% since 2005, because removing infected trees leaves younger, better-managed orchards. So this kg/ha series trends up even as the industry shrinks. Always read it with planted area; never alone.",
    ),
    (
        "br.nonwx.matopiba_algodao",
        "1999→2000년의 도약은 세하두 이전·신품종·규모화·경영의 생산 체계 전환이지 기상 호조가 아닙니다(관개가 아닙니다 — 브라질 면화 재배면적의 약 92%가 천수답이며, 천수답 섬유 단수 세계 1위입니다). 현대 체계 내부의 최대 비기상 요인은 목화바구미로, 최대 70%까지 감수를 일으키지만 그 압력은 파종기 조율과 방제 프로그램에 달려 있지 기후에 달려 있지 않습니다. MODIS NDVI가 면화 단수 모델에서 추세선 대비 거의 기여하지 못한다는 연구(Johnson, ORNL)도 있어, 위성 식생지수로 이 공백을 메우기는 어렵습니다.",
        "The 1999→2000 jump is a production-system shift (Cerrado expansion, new varieties, scale, management), not favorable weather (and not irrigation — ~92% of Brazilian cotton area is rainfed, world #1 rainfed lint yield). Inside the modern system the largest non-weather driver is boll weevil, which can cut yield up to 70%, but pressure depends on planting timing and spray programs, not climate. Research (Johnson, ORNL) also finds MODIS NDVI adds almost nothing vs trend in cotton yield models, so satellite vegetation indices are a poor fill for this gap.",
    ),
    (
        "br.open.matopiba_algodao",
        "검증되지 않은 가설입니다. 이 모델은 면화에 토양수분·근권 저류량 피처를 하나도 안 씁니다 — 강수·폭염·VPD뿐입니다. MATOPIBA 세하두 토양은 모래질이라(대두 모델의 \"유효수분용량\" 로직이 이걸 전제하지만, 그 처리는 면화가 아니라 대두에만 적용됨) 정확히 강수량만으론 식물이 실제 쓸 수 있는 물을 못 잡는 지역입니다. NASA POWER의 근권 토양수분(GWETROOT) — 예전 brazil_soy_model에서 썼지만 이번 패키지에선 아예 안 불러온 변수 — 을 붙이면 비용 없이 바로 검증 가능합니다. 위성 토양수분(SMAP)이나 GRACE 총저류량을 더하면 더 확장됩니다.",
        "Unvalidated hypothesis. This model uses no soil-moisture or root-zone storage features for cotton — only precip, heat, and VPD. MATOPIBA Cerrado soils are sandy (soy’s “available water capacity” logic assumes this, but that treatment applies to soy only, not cotton), so rainfall alone does not capture plant-available water. Adding NASA POWER root-zone moisture (GWETROOT) — used in the older brazil_soy_model but not fetched in this package — can test this at low cost. Satellite soil moisture (SMAP) or GRACE total storage would extend further.",
    ),
    # --- India non-weather ---
    (
        "in.nonwx.punjab_wheat",
        "펀자브·하리아나 밀은 정책이 날씨만큼 수확량을 흔듭니다. 최저지지가격(MSP) 보장 수매, 관정 전력 보조금, 운하 로테이션 일정이 투입 강도와 파종 시기 자체를 정하며 어떤 기상 피처에도 잡히지 않습니다. 지하수 고갈은 이보다 느리게 진행되는 제약으로, 개별 시즌이 아니라 기술 추세선 자체를 서서히 끌어내리는 방향으로 작용합니다.",
        "In Punjab–Haryana wheat, policy moves yield as much as weather. MSP procurement, tube-well power subsidies, and canal rotation schedules set input intensity and sowing timing — none appear in weather features. Groundwater depletion is a slower constraint that gradually pulls down the technology trend itself, not a single-season shock.",
    ),
    (
        "in.nonwx.mp_soybean",
        "마디아프라데시 대두 재배면적은 대두·옥수수·두류의 상대가격에 따라 해마다 이동합니다. 면적 배분이 바뀌면 날씨가 그대로여도 평균 단수가 달라집니다. 종자 갱신률과 황색모자이크 바이러스 발병 압력도 실질적인 해거리 요인이지만 어떤 기후 피처로도 포착되지 않습니다.",
        "Madhya Pradesh soybean area shifts yearly with relative prices of soy, corn, and pulses. When area mix changes, average yield (per-area) moves even if weather is unchanged. Seed replacement rates and yellow mosaic virus pressure are real year-drivers too, but no climate feature captures them.",
    ),
    (
        "in.nonwx.vidarbha_cotton",
        "이 세트에서 날씨로 가장 설명하기 어려운 작물입니다. 2002년 이후 Bt 면화 전환, 종자 가격·공급, 2015년 무렵부터 확산된 핑크볼웜의 Bt 저항성, 대두·비둘기콩 대비 최저지지가격 상대값이 매년 재배면적과 투입 강도를 움직입니다. ICRISAT은 면화를 섬유(lint) 기준으로 발표하므로, 조면율(ginning ratio)이 바뀌기만 해도 밭에서 아무 변화가 없어도 수치가 움직입니다.",
        "Hardest crop in this set to explain with weather. Post-2002 Bt cotton adoption, seed price/supply, pink bollworm Bt resistance spreading from ~2015, and MSP relatives vs soy/pigeonpea move planted area and input intensity every year. ICRISAT publishes cotton on a lint basis, so a ginning-ratio change moves the series with no field change.",
    ),
    # --- method one-liners ---
    (
        "br.method.skeleton",
        "기후 모델링 문서(Regions/브라질) 지역별 수식 구현 · log 추세 + 기상편차",
        "Climate modeling doc (Regions/Brazil) regional formulas · log trend + weather anomaly",
    ),
    (
        "in.method.skeleton",
        "기후 모델링 문서(Regions/인도) 지역별 수식 구현 · log 추세 + 기상편차",
        "Climate modeling doc (Regions/India) regional formulas · log trend + weather anomaly",
    ),
    (
        "us.inputs.summary",
        "수확량 공식통계 + NASA POWER 기상 + (해당 시) ENSO/토양수분 파생",
        "Official yield stats + NASA POWER weather + (where used) ENSO/soil-moisture derivatives",
    ),
    # --- climate panel chrome (phase 2 short bodies) ---
    ("panel.units_howto", "단위 읽는 법 (기관 vs 자사 모델)", "How to read units (agencies vs our models)"),
    ("panel.unit_mmt", "MMT (백만 톤)", "MMT (million tonnes)"),
    ("panel.unit_relation", "관계", "Relationship"),
    ("panel.regions_jump", "산지 바로가기", "Jump to producing regions"),
    ("panel.models_used", "사용 모델", "Models in use"),
    ("panel.units", "단위", "Units"),
    ("panel.conversion", "환산 계수", "Conversion factors"),
    ("panel.bu_soy_wheat", "대두·밀 1 bu", "Soy · wheat 1 bu"),
    ("panel.trade_export", "무역 · 수출 통제", "Trade · export control"),
    ("panel.trade_status", "무역 상태", "Trade status"),
    ("panel.avg_yield_outlook", "평균 단수 전망", "Average yield (per-area) outlook"),
    ("panel.forecast_json_refresh", "예측 JSON 갱신", "Forecast JSON refresh"),
    ("panel.gdd", "적산온도(GDD)", "Growing degree days (GDD)"),
    ("panel.gdd_unit", "{0} 도일", "{0} degree-days"),
    ("panel.precip_anom", "강수량 편차", "Precipitation anomaly"),
    ("panel.temp_anom_seed", "기온 편차 seed", "Temperature-anomaly seed"),
    ("panel.target_region", "대상 지역", "Target region"),
    ("panel.data_asof", "데이터 시점", "Data as-of"),
    ("panel.item", "항목", "Item"),
    ("panel.share_hint", "비중% · 막대는 상대 물동량 · 국가를 누르면 그 나라 노선만 남습니다", "Share % · bars are relative volume · click a country to keep only its routes"),
    ("panel.vs_last_year", "전년 대비 {0}", "Vs prior year {0}"),
    ("panel.actual_year", "{0} 실적", "{0} actual"),
    ("panel.season_outlook", "{0} 예상", "{0} outlook"),
    ("panel.actual_yield", "실적 {0} {1}", "Actual {0} {1}"),
    ("panel.low_conf_share", " · 저신뢰 {0}%", " · low-confidence {0}%"),
    ("panel.stage_not_yet", "해당 생육 단계가 아직 도래하지 않아 예측하지 않음", "No forecast — that growth stage has not arrived yet"),
    ("panel.bottom_up_done", "🌎 각 지역 데이터 상향식(Bottom-up) 통합 산출 완료", "🌎 Bottom-up regional data integrated"),
    ("panel.iod", "IOD · 인도양 쌍극자", "IOD · Indian Ocean Dipole"),
    ("panel.crops_regional", "산지 작물 (지역 단위)", "Producing-region crops (regional)"),
    ("panel.monitor_formula", "모니터 산식", "Monitor formula"),
    ("panel.within_10pct", "−10% 이내", "Within −10%"),
    # --- shipping phase-2 bodies ---
    (
        "ship.desc.fleet",
        "UNCTAD 관측 기준으로 세계 상선 선복량과 선종별 구성을 확인합니다.",
        "World merchant fleet capacity and vessel-type mix from UNCTAD observations.",
    ),
    (
        "ship.desc.routes",
        "연간 화물톤과 왕복 운항주기로 항로에 묶이는 필요 선복량을 추정합니다.",
        "Estimates required fleet capacity tied to a route from annual cargo tonnes and round-trip cycle.",
    ),
    (
        "ship.desc.chokepoints",
        "IMF PortWatch 최근 7일 통항 capacity를 직전 28일 기준선과 비교합니다.",
        "Compares IMF PortWatch last-7-day transit capacity to the prior-28-day baseline.",
    ),
    (
        "ship.desc.scenarios",
        "봉쇄율과 기간을 바꿔 우회·대기·취소가 선복량에 미치는 영향을 계산합니다.",
        "Varies blockade rate and duration to compute how reroute, wait, and cancel affect required fleet capacity.",
    ),
    (
        "ship.err.response",
        "선복량 데이터 응답 오류 ({0})",
        "Fleet-capacity data response error ({0})",
    ),
    (
        "ship.err.version",
        "지원하지 않는 선복량 데이터 버전입니다.",
        "Unsupported fleet-capacity data version.",
    ),
    (
        "ship.capacity_driver",
        "현재 기준 방향은 {0}입니다.",
        "Current baseline direction is {0}.",
    ),
    ("ship.uncertainty_help", "불확실성 구간 설명", "Uncertainty-band notes"),
    ("ship.roundtrip_check", "왕복 주기 입력 확인", "Confirm round-trip cycle inputs"),
    (
        "ship.formula.max",
        "필요 DWT = max(방향별 연간 화물톤 ÷ 적재율) × 왕복주기 ÷ 365",
        "Required DWT = max(annual cargo tonnes by direction ÷ utilization) × round-trip days ÷ 365",
    ),
    (
        "ship.formula.simple",
        "필요 DWT = 연간 화물톤 × 왕복주기 ÷ (365 × 적재율)",
        "Required DWT = annual cargo tonnes × round-trip days ÷ (365 × utilization)",
    ),
    ("ship.route_shock", "항로별 충격", "Shock by route"),
    ("ship.route_compare", "항로별 비교표", "Route comparison table"),
    ("ship.analyze_route", "분석 항로", "Route to analyze"),
    # --- perennial calendar notes ---
    (
        "cal.note.palm_id",
        "연중 수확 (10~14일 주기 수확)",
        "Year-round harvest (10–14 day cutting cycle)",
    ),
    (
        "cal.note.rubber_id",
        "연중 채취 (수액 채취, 저수기 2~3월 감소)",
        "Year-round tapping (latex; declines in dry season Feb–Mar)",
    ),
    (
        "cal.note.rubber_vn",
        "연중 채취 (낙엽기 2~4월 채취 중단)",
        "Year-round tapping (stops in defoliation window Feb–Apr)",
    ),
    (
        "cal.note.cocoa_gh",
        "다년생 · 주수확 10~2월, 중간수확 5~8월",
        "Perennial · main crop Oct–Feb, mid crop May–Aug",
    ),
    (
        "cal.note.cocoa_ci",
        "다년생 · 주수확 10~3월, 중간수확 4~8월",
        "Perennial · main crop Oct–Mar, mid crop Apr–Aug",
    ),
    # --- live weather / misc panel ---
    (
        "wx.live_line",
        "실시간 날씨: 🌡️ {0}°C, 🌬️ {1}km/h (기후 API 연동 중)",
        "Live weather: 🌡️ {0}°C, 🌬️ {1} km/h (climate API linking)",
    ),
    (
        "wx.crop_api_ok",
        "| 🌽 작황 API 연동 성공",
        "| 🌽 Crop-conditions API linked",
    ),
    ("index.global_soy", "글로벌 대두 (Global Soybeans Index)", "Global soybeans index"),
    ("crop.corn_safrinha", "옥수수 (corn - safrinha)", "Corn (safrinha)"),
    ("crop.soy_label_en", "대두 (soybeans)", "Soybeans"),
]


def main() -> None:
    ko = json.loads(KO_PATH.read_text(encoding="utf-8"))
    en = json.loads(EN_PATH.read_text(encoding="utf-8"))

    # preserve meta
    ko_meta = {k: ko.pop(k) for k in list(ko) if str(k).startswith("__")}
    en_meta = {k: en.pop(k) for k in list(en) if str(k).startswith("__")}

    keys = [k for k, _, _ in PAIRS]
    assert len(keys) == len(set(keys)), "duplicate phase2 keys"

    overlap = [k for k in keys if k in ko]
    if overlap:
        raise SystemExit(f"phase2 keys collide with existing: {overlap[:10]}")

    for k, ko_v, en_v in PAIRS:
        ko[k] = ko_v
        en[k] = en_v

    # update meta
    ko_meta["__phase__"] = "1+2"
    en_meta["__phase__"] = "1+2"
    notes = en_meta.get("__notes__", "")
    en_meta["__notes__"] = (
        "Phases 1–2: UI chrome + panel body/essays for Claude t()+lang toggle. "
        "Do not rename keys without bumping both files. Phase 3 = model.yaml label_en/status_note_en."
    )

    def dump(path: Path, data: dict, meta: dict) -> None:
        ordered = dict(sorted(data.items(), key=lambda kv: kv[0]))
        ordered.update(meta)
        path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dump(KO_PATH, ko, ko_meta)
    dump(EN_PATH, en, en_meta)
    print(f"added {len(PAIRS)} phase-2 keys")
    print(f"total content keys: {sum(1 for k in ko if not str(k).startswith('__'))}")


if __name__ == "__main__":
    main()
