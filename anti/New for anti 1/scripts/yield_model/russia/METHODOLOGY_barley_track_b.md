# Russia barley — Track B (oblast) + interim PSD honesty

**Goal:** spring-barley–dominated RF belts (South / CBE / Volga) with **Rosstat/EMISS oblast yields** + NASA POWER weather (ridge + log trend).  
**This pass (2026-08-05):** oblast labels still blocked → train **explicit INTERIM PSD national** targets against zone weather. **Not** Track B validation. **No forecast publish.**

---

## 1. Literature → features

| Source | Takeaway |
|--------|----------|
| MSU WOFOST RU barley hybrids | Process phenology / stress windows — benchmark only |
| Altai GAU 2025 ML | Sep–Mar prior precip; monthly T/P |
| Non-chernozem GTK | May–Aug precip/GTK positive |
| Ryazan / Ob | Mid-May→Jul moisture; June T |

`climate.spring_barley_features`: `precip_may_jul`, `gtk_may_jul`, `sm_*`, `tmax_jun`, `edd_jun_jul`, `precip_sep_mar`, …

---

## 2. Labels

| Mode | Source | When |
|------|--------|------|
| **Track B (desired)** | fedstat **31328** oblast ячмень yield (+ sown area) | `training/oblast_barley_yields.csv` present |
| **INTERIM (this pass)** | USDA FAS PSD Russia **Barley** Yield, ≤2024 | CSV absent |

### Why Track B still blocked

| Attempt | Result |
|---------|--------|
| tochno-st yearbook | No barley-specific yield |
| Zenodo EMISS | Barley rows, empty cells |
| Live fedstat 31328 | **403** |
| Wayback excel | **404** |

### INTERIM limitations (read before trusting any skill number)

1. **National y, zone weather** — Siberia / Urals production moves national yield while South/CBE/Volga points do not see that weather.
2. Same PSD series is attached to **all three** region keys → zone comparison is **not** independent label validation.
3. Forward-chaining skill vs trend is still computed and reported, but `beats_trend` for forecast is **forced false** when `label_resolution=national_psd_interim` even if raw skill > 0.
4. Never claim “oblast Track B skill” from this pass.

---

## 3. Pipeline

```bash
cd "New for anti/scripts/yield_model"
# Optional Track B drop:
#   russia/training/oblast_barley_yields.csv
#   russia/training/oblast_barley_sown_area.csv
python3 -m russia.collect southern_spring_barley cbe_spring_barley volga_spring_barley
python3 -m russia.train  southern_spring_barley cbe_spring_barley volga_spring_barley
# forecast only after oblast labels + honest usable skill
```

---

## 4. Validation gate

| Gate | Rule |
|------|------|
| Sample | regime ≥2000; PSD max year 2024 (drop unfinished estimates) |
| Folds | forward-chaining; trend refit inside fold; skill vs trend |
| Usable | `beats_trend` **and** `label_resolution=oblast` |
| INTERIM | report raw skill; refuse usable / no `run_forecast` for barley |

### INTERIM train results (2026-08-05)

n=25 seasons (2000–2024), forward-chaining, **same national PSD y** for all zones.

| Region key | recent skill vs trend | raw beats? | Honest verdict |
|------------|----------------------:|------------|----------------|
| southern_spring_barley | −0.1% | no | **not usable** — INTERIM / not Track B |
| cbe_spring_barley | −1.9% | no | **not usable** — INTERIM / not Track B (ridge≈trend) |
| volga_spring_barley | −12.2% | no | **not usable** — INTERIM / not Track B |

No barley forecast run (skill gate + label quality both fail).

---

## 5. Remaining for true Track B

1. Researcher download 31328 (or EMISS barley cube) → fill CSV templates.
2. Re-collect / re-train; require positive skill vs trend on **oblast** labels.
3. Then forecast; South winter-barley share caveat if needed.
