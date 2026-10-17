# Indonesia climate-to-production models

This package implements the immediate forecasting objective: measure whether
historical climate deviations explain Indonesian crop yield/production after a
technology trend is removed, and use only relationships that beat a trend-only
forecast in forward chaining.

It covers four national FAOSTAT commodities:

| key | target commodity | climate geography |
|---|---|---|
| `indonesia_rice` | Rice | Java + South Sulawesi + South Sumatra |
| `indonesia_oil_palm` | Oil palm fruit (FFB) | Sumatra + Kalimantan |
| `indonesia_coffee` | Coffee, green | six main coffee belts |
| `indonesia_rubber` | Natural rubber in primary forms | Sumatra + Kalimantan |

The label remains national because a consistent 40-year open province series
is not yet wired in. The weather is not a national centroid: crop features are
derived at multiple production points first and then weighted. This is the
first defensible baseline; BPS province panels can later replace the label
without changing the model/output contract.

## Run

From `scripts/yield_model`:

```bash
PYTHONPATH=. python3 -B -m indonesia.collect
PYTHONPATH=. python3 -B -m indonesia.train
PYTHONPATH=. python3 -B -m indonesia.backtest --years 5
PYTHONPATH=. python3 -B -m indonesia.predict --year 2026
PYTHONPATH=. python3 -B -m indonesia.run_forecast 2026
```

Artifacts:

- `training/*.csv`: annual raw climate features, prior-20-year anomalies, and
  FAOSTAT yield/area/production.
- `models/*.json`: coefficients and measured forward-chaining skill.
- `public/data/indonesia_yield_forecast.json`: current yield, area and total
  production forecast with 68%/95% ranges.

## Method

For each target (yield, harvested area and production):

1. Fit a log-linear technology/structural trend inside every historical fold.
2. Convert each crop-specific climate feature to a z score against only the
   preceding 20 seasons.
3. Fit ridge regression to the log deviation from trend. Ridge strength is
   selected by leave-one-out inside the training fold.
4. Forward-chain one year at a time and compare with the trend-only baseline.
5. Stop the climate adjustment unless there are at least 25 complete seasons
   and at least five seasons per fitted weather parameter, and recent forward
   skill is at least 10% better than trend alone.
6. Stop the operational forecast itself when the recent five-fold MAPE exceeds
   15%. A rejected value may remain as a diagnostic trend, but its public point
   estimate and interval are null.

## Variables by crop and geography

All weather variables are calculated at each point first, combined with the
listed production weights, and converted to a z score using only the preceding
20 seasons. NOAA ONI for the preceding Indonesian dry season is an additional
candidate control. These are hypotheses tested by validation, not assumed
causal relationships.

### Rice — Java, South Sulawesi and South Sumatra

Points: Indramayu (24%), Grobogan (23%), Ngawi (25%), Sidrap (16%) and
Banyuasin (12%). Candidate variables are wet-season onset delay; October–March
rainfall; January–March root-zone soil moisture; extreme degree-days above
33°C; January–March solar radiation; and the longest January–March dry spell.
The predeclared core set is onset delay, soil moisture, heat and main-season
rainfall. Area additionally tests onset, soil moisture and rainfall.

### Oil palm fruit — Sumatra and Kalimantan

Points: Riau (25%), North Sumatra (18%), South Sumatra (17%), Jambi (13%),
West Kalimantan (12%) and Central Kalimantan (15%). Candidate variables are
June–October root-zone soil moisture one and two years before harvest,
one-year-lag rainfall, maximum vapour-pressure deficit, longest dry spell, and
August–October solar radiation as a limited haze proxy. The core set is lag-1
and lag-2 soil moisture plus lag-1 VPD. Area is trend-only because no defensible
annual weather-to-planted-area mechanism was specified.

### Green coffee — Sumatra, Java and South Sulawesi

Points: Lampung (27%), South Sumatra (23%), Aceh/Gayo (14%), North Sumatra
(14%), East Java (12%) and South Sulawesi (10%). Candidate variables are
July–September soil moisture and VPD before flowering; October–December
rainfall; November–March fungal-risk days and wet days; and wet-season solar
radiation. The core set is pre-flowering soil moisture/VPD, flowering rainfall
and fungal-risk days. Area is trend-only. The national label mixes Arabica and
Robusta, so these variables cannot identify cultivar-specific responses.

### Natural rubber — Sumatra and Kalimantan

Points: South Sumatra (31%), North Sumatra (18%), Riau (14%), Jambi (14%),
West Kalimantan (13%) and South Kalimantan (10%). Candidate variables are
January–April wet tapping days, weather-based fungal-risk days and tapping
rainfall; plus July–October lagged root-zone soil moisture and VPD. The core set
excludes tapping rainfall. Area is trend-only. Disease incidence, rubber price,
labour and tapping intensity are not observed by this weather model.

## Current validation result

The collected table has 39 labelled production seasons through 2024, but the
strict prior-20-year anomaly rule leaves only 19 complete climate-training
seasons. That is below every weather-model sample gate (25–40 seasons depending
on feature count). No Indonesian crop currently receives a climate adjustment.
Rice and coffee may emit a clearly labelled trend-only production baseline
where recent backtests pass. Oil-palm production is stopped because its latest
backtest error exceeds 15%, and rubber production is stopped because both
recent average and latest errors fail the gate. More features or a more complex
AI model would make this small-sample problem worse, not solve it.

The live season is assembled as NASA POWER observation, then 16-day Open-Meteo
temperature/precipitation/radiation forecast, then the prior-20-year daily
climatology. Open-Meteo soil moisture is never used.

## Palm oil (CPO) from USDA PSD

FAOSTAT's oil-palm fruit series is flagged estimated/imputed for recent years
and is nearly a straight line, so no weather variable can explain it (climate
candidate 0.0% against the trend). `palm_psd.py` tests the same dry-season and
ENSO features on USDA FAS PSD crude palm oil production and yield instead
(`training/palm_psd_experiment.json`): over 20 forward folds no feature set
beats the trend there either (best all-season skill +0.7%). The weather signal
in national palm output is real but small against replanting and ageing trees.

What it does give is a publishable production number for the traded product.
FAOSTAT fruit production is stopped by the 15% backtest gate. The forecast JSON
now carries an `indonesia_palm_oil` region: the PSD trend for the next
marketing year (October-September), USDA's own estimate beside it
(`usda_estimate`), and last dry season's ONI as context only. The weekly
workflow `indonesia_yield_forecast.yml` refreshes the PSD slice and the forecast.

## Important limitations

- FAOSTAT's recent oil-palm production/yield is estimated and harvested area is
  imputed; the flags are retained in the training table and forecast JSON.
- National coffee combines Arabica and Robusta, masking different calendars and
  biennial cycles.
- Rubber price and tapping intensity, palm age/replanting, and rice irrigation
  releases are omitted. They are explicitly reported as non-weather drivers.
- The direct production forecast is the headline. `yield × area` is also emitted
  as a cross-check; disagreement diagnoses target/area problems rather than
  being silently averaged away.
- Feature-set selection sees the same forward folds reported in the artifact.
  The season-by-season last-five-year report is therefore a configuration
  backtest, not a fully nested model-selection test.

## 팜유 기상 조건 판정 (`palm_conditions.py`)

팜유(CPO) 생산은 어떤 기상 회귀도 추세를 못 이겨 숫자는 추세 그대로 둔다. 대신
알려진 시차 가뭄 메커니즘 4개를 유리·불리·중립으로 판정해 `weather_conditions`
로 붙인다. 예측치에는 반영하지 않는다.

| 지표 | 시점(목표연도 T 기준) | 불리 조건 |
|---|---|---|
| 건기 최장 무강우 일수 | T-1년 6~10월 | z ≥ +0.75 |
| 건기 강수량 | T-1년 6~10월 | z ≤ −0.75 |
| ONI (엘니뇨) | T-1년 건기 | ≥ +0.5 |
| 뿌리층 토양수분 | T-2년 6~10월 | z ≤ −0.75 |

z 는 직전 20개 시즌(최소 10) 대비. 불리 지표가 2개 이상이면(점수 ≤ −2) 종합
"불리", 아니면 "중립". 건기가 아직 진행 중이면 모든 해를 같은 날짜까지 잘라
비교한다(반쯤 지난 시즌을 가뭄으로 오판하지 않도록).

임계값은 결과를 보기 전에 정했다. 1996~2025 USDA PSD 기준
(`training/palm_conditions_backtest.json`): 불리 판정 4번(1998·2016·2020·2024)
모두 생산이 직전 10년 추세보다 낮았고 평균 −14.8% (중립 해 −3.1%).
습윤·라니냐 쪽(점수 ≥ +2, 7번)은 평균 −7.1% 로 오히려 낮아 "유리" 종합 판정은
내지 않는다.

```bash
python -m indonesia.palm_conditions backtest   # 오프라인 재검증
```
