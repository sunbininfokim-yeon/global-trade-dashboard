# Resume here

State as of 2026-08-03. Nothing is mid-edit; the tree is consistent and every
command below is safe to run cold.

---

## 1. FIXED — windowed-trend intercept bug (2026-08-03)

`window_rows()` in `train.py` now narrows the regression to the rows the trend
was fitted to. Verified: all ten models report an intercept of exactly 0.

Effect on results: `mato_grosso_milho` +40.4% -> +24.5%, `parana_trigo`
+11.1% -> +0.7%, `sp_cana` +8.2% -> -13.6%, `matopiba_soja` -17.7% -> -1.3%,
`mato_grosso_soja` -9.4% -> +5.4%. `parana_soja` unchanged at +49.0% as
predicted (deg1, never affected). Tables in README.md are post-fix.

## 2. Orange — built, validated and published

`sp_laranja` is fully built (config, SIDRA code `laranja` → table 1613 / c82 /
2733, training table, model JSON). Two findings are already encoded in it:

- **`regime_start=2001`.** IBGE switched the orange unit from thousands of
  fruits to tonnes between 2000 and 2001: yield drops 84% in one year
  (145,999 → 23,267 kg/ha) and stays. Reporting change, not agronomy.
- **kg/ha is the wrong lens for this crop.** HLB kills trees, not per-hectare
  yield. São Paulo orange area is down 55% from its 1991 peak (789,329 →
  354,562 ha) while yield on surviving area rose 35% since 2005. A kg/ha
  forecast shows a healthy rising crop while the industry contracts.

The guide itself opens by saying the market is collapsing *"기후가 아닌"* —
not from climate — but from citrus greening, and prescribes drone CNN and a
spatial contagion model. `non_weather_drivers` carries that, and the dashboard
prints it in Korean beneath the figure.

Post-fix it scores +43.5% forward-chaining but only +1.1pp on the 5-year
holdout, so it is **forward-chaining only, not confirmed**. Treat the number as
provisional.

**Still open:** publishing planted area alongside kg/ha, so the 55% area
collapse is visible next to a rising yield. Recommended, not built.

---

## 3. Not yet done

- **Coffee `lag3` + frost severity.** `Regions/브라질/미나스제라이스/커피` asks
  for a 3-year biennial memory (we carry lag1, lag2) and a Sentinel-2 NDVI
  drop-magnitude feature for frost damage (we carry a frost day count).
  Region coverage is already correct — `sp_cafe` is MG 0.75 / SP 0.25.
- **Planted-area context for oranges** (see section 2).
- **Sugar/ethanol allocation.** The new guide says the decisive variable is the
  mill's sugar-vs-ethanol mix, driven by crude oil and BRL. That is an
  economic model, not a weather one, and is out of scope for this package.

---

## 4. Uncommitted work

```
.github/workflows/brazil_yield_forecast.yml   weekly run + auto-retrain
New for anti/app.js                            Brazil panel, badges, map regions
New for anti/data.js                           loader + MATOPIBA/SP coordinates
New for anti/scripts/yield_model/brazil/       README.md, NEXT_STEPS.md,
                                               sidra.py, regions.py, models/
```

Also untracked and **not from this work** — check before committing:
`collect_us_wheat.py`, `train_wheat.py`, `us_*_wheat_*.{json,csv}`, and the
newer `yield_model/argentina/`, `yield_model/china/`, `yield_model/india/`
packages with `argentina_yield_forecast.yml`.

Checked, so nobody has to check again: `argentina/train.py` imports `run_cv`,
`fit_trend`, `prepare` and `evaluate` straight from `brazil/train.py`, so its
**validation already inherits the `window_rows()` fix** — no retrain needed.
Its final model fit is its own code (lines ~185-187) and still lacks the window
restriction, so the bug is latent there. It has not bitten: all five Argentine
models selected deg1/deg2 and report an intercept of exactly 0. It will bite
the first time one of them selects recent10/recent20. `china/` and `india/`
have no `train.py` yet.

---

## 6. Municipality-level MATOPIBA soy -- tried, negative result (2026-08-03)

New isolated module: `brazil/matopiba_municipal.py`. Deliberately does not
touch collect.py/climate.py/regions.py/predict.py/run_forecast.py beyond
importing from them, to avoid compounding the concurrent-session merge
conflict on those files (see section 4) -- only `sidra.py` got one new
function (`municipality_yield`, n6-level SIDRA query), and that file was
untouched by the other session.

**Feasibility check (done first, before building):** IBGE SIDRA has
municipality-level (n6) yield for both soja and algodão across all 13
candidate MATOPIBA municipalities geocoded for this experiment. Completeness
is good -- every candidate has 100% coverage for 2015-2024, and 27-45 years
total depending on when each municipality was administratively created
(Luís Eduardo Magalhães, split off in 2000, only has 24 years -- excluded).
Coordinates + elevations for all 13 are in `MUNICIPALITIES` in the new
module.

**Result: negative, consistent across 4 municipalities tested.**

| municipality | seasons | vs trend (recent) | 5yr holdout MAPE | verdict |
|---|---:|---:|---|---|
| balsas (MA) | 41 | -1.7% | 9.2% vs 8.7% | no skill |
| correntina (BA) | 39 | -6.6% | 5.2% vs 5.1% | no skill |
| barreiras (BA) | 41 | -12.4% | 6.7% vs 4.0% | no skill |
| sao_desiderio (BA) | 41 | -21.5% | 5.8% vs 3.6% | no skill |

All four fail both evaluations. Barreiras and São Desidério are two of Reis
et al.'s (2020) own four validation municipalities, where DSSAT-CROPGRO (a
mechanistic crop simulator) was reported to have "good predictive capacity"
-- so the same locations that work for a process-based model do not work for
this statistical one.

**What this actually tells us:** the working hypothesis going in was "state
aggregation hides a real municipality-level signal." This experiment argues
against that. If aggregation were the main problem, splitting to municipality
level should have recovered skill at least somewhere in 4 tries; it didn't,
not even at Reis et al.'s own sites. The more likely explanation: the
modelling *approach* -- linear/ridge regression on a handful of monthly
aggregate features (heat days, VPD stress, mean root-zone wetness) -- is not
expressive enough to capture what a day-by-day mechanistic water-balance
simulator captures, regardless of spatial grain. Aggregating four states into
one number was never free of cost, but de-aggregating alone does not buy back
what a simple regression is structurally missing.

**Not yet tested:** the remaining 8 candidate municipalities (MA/PI/TO), and
cotton at municipality level (data confirmed available for the BA
municipalities, unused). Given four consistent negative results including two
literature-validated sites, running the rest is unlikely to change the
conclusion, but it would need doing before writing off municipality-level
statistical modelling entirely rather than just this pilot's feature set.

**If MATOPIBA soy is to work at all, the literature's own answer is to change
architecture, not resolution:** a mechanistic model (DSSAT-CROPGRO or
AquaCrop, both independently validated for MATOPIBA soy) rather than a
statistical regression, at any spatial grain. That is materially more work
than anything tried so far in this package (a full crop simulator needs
cultivar genetic coefficients, daily soil-layer water balance, phenology
staging) and was not attempted here.

## 7. MATOPIBA ML(RF/XGBoost) 실험 -- 미미한 개선, 결론 유지 (2026-08-04)

새 파일: `brazil/matopiba_ml_experiment.py`. 새 데이터 수집 없음 -- 6번 섹션에서
이미 모은 state-level matopiba_soja + 지자체 4곳 데이터에 ridge 대신
RandomForestRegressor/XGBRegressor를 얹어 같은 forward-chaining 규율로 재검증.
(Barbosa dos Santos et al. 2022, *J. Sci. Food Agric.* 102(9):3665-3672 --
MATOPIBA 대두를 정확히 같은 데이터 소스(NASA POWER+SIDRA)로 예측, RF 최고
R²=0.81, RMSE 176.93 kg/ha 보고 -- 를 재현할 수 있는지가 동기.)

| 데이터 | ridge (6번 실험) | RF | XGBoost |
|---|---:|---:|---:|
| 주(州) matopiba_soja | -1.3%~+1.6% | -2.6% | -10.8% |
| balsas | -1.7% | +0.9% | +10.6% |
| barreiras | -12.4% | +1.0% | -9.3% |
| correntina | -6.6% | -3.4% | -27.6% |
| sao_desiderio | -21.5% | -15.1% | -29.5% |

RF는 5곳 중 4곳에서 ridge보다 나았고 2곳(balsas, barreiras)은 약하게 추세선을
이겼지만(+0.9%, +1.0%), 파라나 대두(+49%)급과는 비교가 안 되는 수준. XGBoost는
대체로 더 나쁘고 변동폭도 큼 -- 작은 표본(N~40)에서 부스팅이 배깅보다 과적합에
취약하다는 일반적 문헌(Meroni et al. 2021)과 일치.

**RMSE 435~664 kg/ha로, Barbosa dos Santos의 177 kg/ha와 2.5~4배 차이.** 같은
데이터인데 이 정도 차이가 난다는 건 그쪽이 이만큼 엄격한 시간순 홀드아웃을 안
썼을 가능성이 높다는 뜻 -- 논문 전문을 못 봐서(paywall) 확인은 못 함.

**결론: ML로의 전환도 근본 해결책은 아니었음.** 오늘 시도한 세 축(GWETROOT 추가,
지자체 분할, 모델 교체) 전부 미미한 개선이거나 무효 -- 공통적으로 "더 나은 입력
하나 추가" 또는 "더 유연한 모델"로는 안 풀림. 위성 NDVI(다음 후보)도 구조적으로
같은 범주라 큰 반전은 기대하기 어렵다고 판단, API 비용(MODIS 요청당 10개 시점
제한, 지자체당 수십 회) 대비 기대값이 낮아 보류.

**진짜 검증된 해법은 문헌상 하나뿐**: DSSAT-CROPGRO/AquaCrop 같은 일 단위
작물생리 시뮬레이터 (Reis et al. 2020; da Silva et al. 2018) -- 품종별 유전계수·
토양층 보정이 필요해 지금까지 시도보다 스코프가 훨씬 큼. MATOPIBA는 여기서
보류하고 다른 지역/국가 작업을 먼저 마친 뒤 재검토하기로 함.

## 5. Settled, do not redo

- Sugarcane is not a weather problem. Our `weather_skill` −13.6% (`lag1`'s own
  effect is +0.1%, the weakest of eleven features -- even the management
  proxy barely moves it), Dias & Sentelhas (2017) getting MAE > 29 t/ha and
  R² < 0.54 from FAO-AZM, DSSAT/CANEGRO and APSIM until a ratoon-decline
  factor is added, and the new guide itself pointing at the sugar/ethanol mix
  — three independent routes to the same conclusion.
- Satellite data should not be added for cotton or cane. Johnson (ORNL) finds
  MODIS NDVI adds little for upland cotton while transforming corn
  (R² 0.93 vs 0.48). If satellite effort is spent, spend it on corn.
- Cotton's pre-2000 era is a different farming system and stays excluded
  (`regime_start=2000`). Brazil cotton is ~92% rainfed — the 2000 break was
  relocation, cultivars and scale, not irrigation.
- **MATOPIBA GWETROOT (Step 1 of the soil-moisture work order): tried, does
  not help, reverted (2026-08-03).** Root-zone wetness (NASA POWER GWETROOT)
  was added for both `matopiba_soja`'s reproductive window and
  `matopiba_algodao`'s ADD-based flowering window, plus a "hot AND dry"
  cross-term at the wilting-point thresholds the work order specified (0.3
  soy, 0.2 cotton). Finding: **those thresholds never bind.** Across all
  41-43 seasons at all four MATOPIBA points, root-zone wetness in the
  relevant window never drops below 0.48 -- the cross-term and the
  stress-day count are constant zero, always. This is the rainy season; the
  "hot and dry" event the guide hypothesises for this specific window simply
  is not present in this 1981-2024 reanalysis record at these points.
  Retraining with the surviving `gwetroot_*_mean` feature alone moved
  forward-chaining skill (soy −1.3%→+1.6%, cotton +14.6%→+47.2%), but the
  **5-year holdout contradicted both** (soy 7.7%→15.5% MAPE, cotton
  2.6%→8.9% MAPE -- both worse), and the mean-wetness feature's own
  standardised effect was the smallest or second-smallest term in each model
  (+0.36% cotton, −0.40% soy). Read together: the forward-chaining gain was
  noise from a slightly different candidate set on small samples (25-41
  seasons), not a real signal. The two model JSONs were reverted to the
  pre-GWETROOT, holdout-confirmed state via `git checkout`. The code
  (`collect.py`/`predict.py` fetch `GWETROOT` into a `soil` column;
  `climate.py` has the helper functions; `regions.py`'s build functions
  compute the features) is left in place -- harmless, and reusable if Step 2
  (SMAP) is tried later with a threshold actually calibrated to what this
  record shows (something above 0.48, not 0.2-0.4). Do not re-attempt Step 1
  with the work order's thresholds unchanged; they are empirically wrong for
  this window at these points.
